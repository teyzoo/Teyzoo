from __future__ import annotations
import logging
from dataclasses import dataclass
from config import (
    DEFAULT_PAIRS,
    MARKET_CANDLE_LIMIT,
    TIMEFRAMES,
)
from market import (
    MarketClient,
    MarketDataError,
    MarketRateLimitError,
)
from quality_filter import (
    QualityFilter,
    QualityResult,
    analyze_timeframe,
)
logger = logging.getLogger("pair_selector")
# =========================================================
# DATA MODEL
# =========================================================
@dataclass(slots=True)
class PairAnalysis:
    symbol: str
    result: QualityResult
# =========================================================
# PAIR SELECTOR
# =========================================================
class PairSelector:
    """
    Выбор лучшей торговой пары.
    Основные задачи:
    1. Получить свечи по нескольким таймфреймам.
    2. Проанализировать каждый таймфрейм.
    3. Передать результаты в QualityFilter.
    4. Отобрать только качественные пары.
    5. Выбрать лучшую пару.
    ВАЖНО:
    Twelve Data имеет ограничение API credits/minute.
    Поэтому PairSelector специально НЕ запускает
    анализ всех пар параллельно.
    Пары анализируются последовательно.
    Если MarketClient сообщает о rate limit (HTTP 429),
    текущий проход полностью прекращается.
    Это предотвращает ситуацию:
        429
        ↓
        следующая пара
        ↓
        ещё запрос
        ↓
        ещё ожидание
        ↓
        следующая пара
    Вместо этого:
        429
        ↓
        остановка текущего сканирования
        ↓
        следующий scheduler cycle
    """
    def __init__(
        self,
        market: MarketClient,
        quality_filter: QualityFilter,
    ) -> None:
        self.market = market
        self.quality_filter = quality_filter
    # =====================================================
    # ANALYZE ONE PAIR
    # =====================================================
    async def analyze_pair(
        self,
        symbol: str,
    ) -> PairAnalysis:
        """
        Полный анализ одной пары.
        Для пары загружаются все TIMEFRAMES,
        после чего каждый timeframe анализируется
        отдельно.
        Например:
            EUR/USD
              ├── 1m
              ├── 5m
              └── 15m
        """
        symbol = str(symbol).strip().upper()
        if not symbol:
            raise ValueError(
                "Pair symbol cannot be empty."
            )
        logger.info(
            "Analyzing pair: %s",
            symbol,
        )
        # =================================================
        # LOAD MARKET DATA
        # =================================================
        try:
            timeframe_data = (
                await self.market.get_multi_timeframe(
                    symbol=symbol,
                    timeframes=TIMEFRAMES,
                    limit=MARKET_CANDLE_LIMIT,
                )
            )
        except MarketRateLimitError:
            # -------------------------------------------------
            # Критическая ошибка для текущего прохода.
            #
            # Не превращаем её в обычную ошибку пары.
            # Передаём наверх find_best_pair().
            # -------------------------------------------------
            logger.warning(
                "Market API rate limit reached "
                "while analyzing %s.",
                symbol,
            )
            raise
        except MarketDataError:
            logger.exception(
                "Market data error while analyzing %s.",
                symbol,
            )
            raise
        except Exception:
            logger.exception(
                "Unexpected market error while analyzing %s.",
                symbol,
            )
            raise
        if not timeframe_data:
            logger.warning(
                "%s: no timeframe data received.",
                symbol,
            )
            raise MarketDataError(
                f"No timeframe data received for {symbol}."
            )
        # =================================================
        # ANALYZE TIMEFRAMES
        # =================================================
        analyses: list[QualityResult] = []
        for timeframe, candles in (
            timeframe_data.items()
        ):
            candle_count = (
                len(candles)
                if candles
                else 0
            )
            logger.info(
                "%s | %s | candles=%s",
                symbol,
                timeframe,
                candle_count,
            )
            # -------------------------------------------------
            # Проверяем количество свечей.
            #
            # analyze_timeframe() всё равно может проверить
            # это самостоятельно, но здесь лучше не передавать
            # заведомо пустые данные.
            # -------------------------------------------------
            if not candles:
                logger.warning(
                    "%s | %s | no candles.",
                    symbol,
                    timeframe,
                )
                continue
            try:
                result = analyze_timeframe(
                    timeframe,
                    candles,
                )
                analyses.append(
                    result
                )
            except Exception:
                logger.exception(
                    "%s | %s | "
                    "timeframe analysis failed.",
                    symbol,
                    timeframe,
                )
                continue
        # =================================================
        # NO ANALYSES
        # =================================================
        if not analyses:
            logger.warning(
                "%s: no timeframe analyses produced.",
                symbol,
            )
            raise MarketDataError(
                f"No timeframe analyses for {symbol}."
            )
        # =================================================
        # QUALITY FILTER
        # =================================================
        try:
            quality = (
                self.quality_filter.evaluate(
                    analyses
                )
            )
        except Exception:
            logger.exception(
                "%s | Quality Filter failed.",
                symbol,
            )
            raise
        # =================================================
        # LOG QUALITY
        # =================================================
        logger.info(
            (
                "%s | Quality Filter | "
                "accepted=%s | "
                "score=%.2f | "
                "confirmations=%s | "
                "direction=%s"
            ),
            symbol,
            quality.accepted,
            quality.quality_score,
            quality.confirmations,
            quality.direction,
        )
        return PairAnalysis(
            symbol=symbol,
            result=quality,
        )
    # =====================================================
    # FIND BEST PAIR
    # =====================================================
    async def find_best_pair(
        self,
        pairs: list[str] | None = None,
    ) -> PairAnalysis | None:
        """
        Анализирует список пар и выбирает лучшую.
        ВАЖНО:
        Анализ выполняется ПОСЛЕДОВАТЕЛЬНО.
        Это сделано специально для Twelve Data,
        чтобы не создавать одновременно большое
        количество API requests.
        При HTTP 429 текущий проход останавливается.
        Например:
            EUR/USD → OK
            GBP/USD → OK
            USD/JPY → OK
            USD/CHF → 429
        После этого:
            текущий проход STOP
        Следующий scheduler cycle сможет продолжить
        работу после сброса API лимита.
        """
        # =================================================
        # SELECT PAIRS
        # =================================================
        selected_pairs = (
            pairs
            if pairs is not None
            else DEFAULT_PAIRS
        )
        # -------------------------------------------------
        # Убираем пустые значения.
        # -------------------------------------------------
        normalized_pairs: list[str] = []
        for symbol in selected_pairs:
            if symbol is None:
                continue
            normalized = (
                str(symbol)
                .strip()
                .upper()
            )
            if not normalized:
                continue
            if normalized not in normalized_pairs:
                normalized_pairs.append(
                    normalized
                )
        logger.info(
            "Starting pair selection. "
            "Pairs=%s",
            len(normalized_pairs),
        )
        if not normalized_pairs:
            logger.warning(
                "No pairs available for selection."
            )
            return None
        # =================================================
        # CANDIDATES
        # =================================================
        candidates: list[PairAnalysis] = []
        # =================================================
        # ANALYZE PAIRS SEQUENTIALLY
        # =================================================
        for index, symbol in enumerate(
            normalized_pairs,
            start=1,
        ):
            logger.info(
                (
                    "Pair scan %s/%s: %s"
                ),
                index,
                len(normalized_pairs),
                symbol,
            )
            try:
                analysis = (
                    await self.analyze_pair(
                        symbol
                    )
                )
            # -------------------------------------------------
            # RATE LIMIT
            # -------------------------------------------------
            except MarketRateLimitError:
                logger.warning(
                    (
                        "Twelve Data rate limit "
                        "reached while scanning %s. "
                        "Stopping current pair scan."
                    ),
                    symbol,
                )
                # -------------------------------------------------
                # КЛЮЧЕВОЕ ИЗМЕНЕНИЕ:
                #
                # НЕ продолжаем следующий symbol.
                #
                # Иначе scheduler будет пытаться делать
                # дополнительные запросы и ждать rate limiter.
                # -------------------------------------------------
                break
            # -------------------------------------------------
            # MARKET DATA ERROR
            # -------------------------------------------------
            except MarketDataError as exc:
                logger.warning(
                    (
                        "Market data error for %s: %s. "
                        "Skipping pair."
                    ),
                    symbol,
                    exc,
                )
                continue
            # -------------------------------------------------
            # VALUE ERROR
            # -------------------------------------------------
            except ValueError as exc:
                logger.warning(
                    (
                        "Invalid pair configuration "
                        "for %s: %s. "
                        "Skipping pair."
                    ),
                    symbol,
                    exc,
                )
                continue
            # -------------------------------------------------
            # UNEXPECTED ERROR
            # -------------------------------------------------
            except Exception:
                logger.exception(
                    "Pair analysis failed: %s",
                    symbol,
                )
                continue
            # =================================================
            # SAVE CANDIDATE
            # =================================================
            candidates.append(
                analysis
            )
        # =================================================
        # ANALYSIS COMPLETED
        # =================================================
        logger.info(
            (
                "Pair analysis completed. "
                "Candidates=%s"
            ),
            len(candidates),
        )
        if not candidates:
            logger.info(
                "No pair candidates available."
            )
            return None
        # =================================================
        # ACCEPTED PAIRS
        # =================================================
        accepted = [
            item
            for item in candidates
            if item.result.accepted
        ]
        logger.info(
            (
                "Quality Filter accepted "
                "%s/%s pairs."
            ),
            len(accepted),
            len(candidates),
        )
        # =================================================
        # NO ACCEPTED PAIRS
        # =================================================
        if not accepted:
            logger.info(
                "No pair passed Quality Filter."
            )
            return None
        # =================================================
        # SORT
        # =================================================
        accepted.sort(
            key=lambda item: (
                item.result.quality_score,
                item.result.confirmations,
            ),
            reverse=True,
        )
        # =================================================
        # BEST PAIR
        # =================================================
        best = accepted[0]
        logger.info(
            (
                "Best pair selected: %s | "
                "score=%.2f | "
                "confirmations=%s | "
                "direction=%s"
            ),
            best.symbol,
            best.result.quality_score,
            best.result.confirmations,
            best.result.direction,
        )
        return best
# =========================================================
# EXPORTS
# =========================================================
__all__ = [
    "PairAnalysis",
    "PairSelector",
]
