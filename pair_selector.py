from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Iterable
from config import (
    DEFAULT_PAIRS,
    MARKET_CANDLE_LIMIT,
    TIMEFRAMES,
)
from market import (
    Candle,
    MarketClient,
    MarketDataError,
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
    """
    Результат полного анализа одной торговой пары.
    symbol:
        Нормализованное имя торговой пары.
    result:
        Итог QualityFilter.
    """
    symbol: str
    result: QualityResult
# =========================================================
# PAIR SELECTOR
# =========================================================
class PairSelector:
    """
    Выбирает лучшую торговую пару на основании
    мульти-таймфреймового анализа.
    Работает непосредственно с текущим MarketClient:
        MarketClient.get_multi_timeframe()
    и не использует никаких методов, которых
    нет в твоём текущем market.py.
    """
    def __init__(
        self,
        market: MarketClient,
        quality_filter: QualityFilter,
    ) -> None:
        self.market = market
        self.quality_filter = quality_filter
    # =====================================================
    # NORMALIZE SYMBOL
    # =====================================================
    @staticmethod
    def _normalize_symbol(
        symbol: str,
    ) -> str:
        """
        Нормализует название пары.
        Например:
            eurusd
            EURUSD
            EUR/USD
        превращаются в:
            EUR/USD
        Если символ нестандартный — оставляем
        его в верхнем регистре.
        """
        normalized = str(
            symbol
        ).strip().upper()
        if not normalized:
            raise ValueError(
                "Symbol is required."
            )
        if (
            "/" not in normalized
            and len(normalized) == 6
            and normalized.isalpha()
        ):
            normalized = (
                f"{normalized[:3]}/"
                f"{normalized[3:]}"
            )
        return normalized
    # =====================================================
    # VALIDATE CANDLES
    # =====================================================
    @staticmethod
    def _valid_candles(
        candles: Iterable[Candle] | None,
    ) -> list[Candle]:
        """
        Возвращает только валидные свечи.
        Дополнительная защита перед передачей
        данных в analyze_timeframe().
        """
        if not candles:
            return []
        result: list[Candle] = []
        for candle in candles:
            if candle is None:
                continue
            try:
                if candle.open <= 0:
                    continue
                if candle.high <= 0:
                    continue
                if candle.low <= 0:
                    continue
                if candle.close <= 0:
                    continue
                if candle.high < candle.low:
                    continue
                if not (
                    candle.low
                    <= candle.open
                    <= candle.high
                ):
                    continue
                if not (
                    candle.low
                    <= candle.close
                    <= candle.high
                ):
                    continue
                result.append(candle)
            except (
                AttributeError,
                TypeError,
                ValueError,
            ):
                continue
        return result
    # =====================================================
    # ANALYZE PAIR
    # =====================================================
    async def analyze_pair(
        self,
        symbol: str,
    ) -> PairAnalysis:
        """
        Полностью анализирует одну торговую пару.
        Алгоритм:
        1. Нормализуем symbol.
        2. Получаем свечи сразу по всем TIMEFRAMES.
        3. Для каждого таймфрейма запускаем
           analyze_timeframe().
        4. Передаём результаты в QualityFilter.
        5. Возвращаем PairAnalysis.
        """
        normalized_symbol = (
            self._normalize_symbol(
                symbol
            )
        )
        logger.info(
            "Analyzing pair: %s",
            normalized_symbol,
        )
        # =================================================
        # LOAD MULTI-TIMEFRAME DATA
        # =================================================
        try:
            timeframe_data = (
                await self.market.get_multi_timeframe(
                    symbol=normalized_symbol,
                    timeframes=tuple(
                        TIMEFRAMES
                    ),
                    limit=int(
                        MARKET_CANDLE_LIMIT
                    ),
                )
            )
        except (
            MarketDataError,
            ValueError,
        ) as exc:
            logger.warning(
                (
                    "%s: market data unavailable: %s"
                ),
                normalized_symbol,
                exc,
            )
            raise
        except Exception:
            logger.exception(
                (
                    "%s: unexpected market "
                    "data error."
                ),
                normalized_symbol,
            )
            raise
        # =================================================
        # NO DATA
        # =================================================
        if not timeframe_data:
            logger.warning(
                "%s: no timeframe data received.",
                normalized_symbol,
            )
            raise MarketDataError(
                f"No timeframe data for {normalized_symbol}"
            )
        # =================================================
        # ANALYZE TIMEFRAMES
        # =================================================
        analyses: list[QualityResult] = []
        for timeframe in TIMEFRAMES:
            candles = timeframe_data.get(
                timeframe
            )
            valid_candles = (
                self._valid_candles(
                    candles
                )
            )
            candle_count = len(
                valid_candles
            )
            logger.info(
                (
                    "%s | %s | "
                    "candles=%s"
                ),
                normalized_symbol,
                timeframe,
                candle_count,
            )
            # -------------------------------------------------
            # Insufficient candles
            # -------------------------------------------------
            if candle_count < 20:
                logger.warning(
                    (
                        "%s | %s | "
                        "not enough candles: %s"
                    ),
                    normalized_symbol,
                    timeframe,
                    candle_count,
                )
                continue
            # =================================================
            # ANALYZE TIMEFRAME
            # =================================================
            try:
                result = analyze_timeframe(
                    timeframe,
                    valid_candles,
                )
            except (
                ValueError,
                TypeError,
                MarketDataError,
            ) as exc:
                logger.warning(
                    (
                        "%s | %s | "
                        "timeframe analysis failed: %s"
                    ),
                    normalized_symbol,
                    timeframe,
                    exc,
                )
                continue
            except Exception:
                logger.exception(
                    (
                        "%s | %s | "
                        "unexpected timeframe "
                        "analysis error."
                    ),
                    normalized_symbol,
                    timeframe,
                )
                continue
            # -------------------------------------------------
            # Validate analysis result
            # -------------------------------------------------
            if result is None:
                logger.warning(
                    (
                        "%s | %s | "
                        "analyzer returned None."
                    ),
                    normalized_symbol,
                    timeframe,
                )
                continue
            analyses.append(
                result
            )
            logger.info(
                (
                    "%s | %s | "
                    "timeframe analysis completed."
                ),
                normalized_symbol,
                timeframe,
            )
        # =====================================================
        # NO ANALYSES
        # =====================================================
        if not analyses:
            logger.warning(
                (
                    "%s: no timeframe analyses "
                    "were produced."
                ),
                normalized_symbol,
            )
            raise MarketDataError(
                (
                    f"No valid timeframe analyses "
                    f"for {normalized_symbol}"
                )
            )
        # =====================================================
        # QUALITY FILTER
        # =====================================================
        try:
            quality = (
                self.quality_filter.evaluate(
                    analyses
                )
            )
        except Exception:
            logger.exception(
                (
                    "%s: QualityFilter evaluation failed."
                ),
                normalized_symbol,
            )
            raise
        # =====================================================
        # RESULT LOG
        # =====================================================
        logger.info(
            (
                "%s | Quality Filter | "
                "accepted=%s | "
                "score=%.2f | "
                "confirmations=%s | "
                "direction=%s"
            ),
            normalized_symbol,
            quality.accepted,
            float(
                quality.quality_score
            ),
            quality.confirmations,
            quality.direction,
        )
        return PairAnalysis(
            symbol=normalized_symbol,
            result=quality,
        )
    # =====================================================
    # FIND BEST PAIR
    # =====================================================
    async def find_best_pair(
        self,
        pairs: list[str] | tuple[str, ...] | None = None,
    ) -> PairAnalysis | None:
        """
        Анализирует список пар и возвращает
        лучшую пару, которая прошла QualityFilter.
        Если ни одна пара не прошла фильтр:
            return None
        """
        # =================================================
        # SELECT PAIRS
        # =================================================
        if pairs is None:
            selected_pairs = list(
                DEFAULT_PAIRS
            )
        else:
            selected_pairs = list(
                pairs
            )
        # =================================================
        # REMOVE DUPLICATES
        # =================================================
        normalized_pairs: list[str] = []
        seen: set[str] = set()
        for symbol in selected_pairs:
            try:
                normalized_symbol = (
                    self._normalize_symbol(
                        symbol
                    )
                )
            except ValueError:
                logger.warning(
                    "Skipping invalid pair: %r",
                    symbol,
                )
                continue
            if normalized_symbol in seen:
                continue
            seen.add(
                normalized_symbol
            )
            normalized_pairs.append(
                normalized_symbol
            )
        # =================================================
        # EMPTY PAIRS
        # =================================================
        if not normalized_pairs:
            logger.warning(
                "Pair selection started with no valid pairs."
            )
            return None
        logger.info(
            (
                "Starting pair selection. "
                "Pairs=%s"
            ),
            len(normalized_pairs),
        )
        # =================================================
        # ANALYZE ALL PAIRS
        # =================================================
        candidates: list[PairAnalysis] = []
        for symbol in normalized_pairs:
            try:
                analysis = (
                    await self.analyze_pair(
                        symbol
                    )
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    (
                        "Pair analysis failed: %s"
                    ),
                    symbol,
                )
                continue
            candidates.append(
                analysis
            )
        # =================================================
        # NO CANDIDATES
        # =================================================
        logger.info(
            (
                "Pair analysis completed. "
                "Candidates=%s/%s"
            ),
            len(candidates),
            len(normalized_pairs),
        )
        if not candidates:
            logger.info(
                "No pair analyses completed successfully."
            )
            return None
        # =================================================
        # FILTER ACCEPTED
        # =================================================
        accepted = [
            item
            for item in candidates
            if bool(
                item.result.accepted
            )
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
        def ranking_key(
            item: PairAnalysis,
        ) -> tuple[
            float,
            int,
            int,
        ]:
            """
            Приоритет:
            1. quality_score
            2. confirmations
            3. количество анализируемых свечей
            Последний параметр используется только
            как дополнительный tie-breaker.
            """
            try:
                score = float(
                    item.result.quality_score
                )
            except (
                TypeError,
                ValueError,
            ):
                score = 0.0
            try:
                confirmations = int(
                    item.result.confirmations
                )
            except (
                TypeError,
                ValueError,
            ):
                confirmations = 0
            return (
                score,
                confirmations,
                0,
            )
        accepted.sort(
            key=ranking_key,
            reverse=True,
        )
        # =================================================
        # BEST
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
            float(
                best.result.quality_score
            ),
            best.result.confirmations,
            best.result.direction,
        )
        return best
    # =====================================================
    # FIND ALL ACCEPTED PAIRS
    # =====================================================
    async def find_accepted_pairs(
        self,
        pairs: list[str] | tuple[str, ...] | None = None,
    ) -> list[PairAnalysis]:
        """
        Возвращает ВСЕ пары, прошедшие QualityFilter.
        В отличие от find_best_pair():
            find_best_pair()
                -> одна лучшая пара
            find_accepted_pairs()
                -> все подходящие пары
        """
        if pairs is None:
            selected_pairs = list(
                DEFAULT_PAIRS
            )
        else:
            selected_pairs = list(
                pairs
            )
        normalized_pairs: list[str] = []
        seen: set[str] = set()
        for symbol in selected_pairs:
            try:
                normalized_symbol = (
                    self._normalize_symbol(
                        symbol
                    )
                )
            except ValueError:
                logger.warning(
                    "Skipping invalid pair: %r",
                    symbol,
                )
                continue
            if normalized_symbol in seen:
                continue
            seen.add(
                normalized_symbol
            )
            normalized_pairs.append(
                normalized_symbol
            )
        accepted: list[PairAnalysis] = []
        for symbol in normalized_pairs:
            try:
                analysis = (
                    await self.analyze_pair(
                        symbol
                    )
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    (
                        "Pair analysis failed: %s"
                    ),
                    symbol,
                )
                continue
            if analysis.result.accepted:
                accepted.append(
                    analysis
                )
        # =================================================
        # SORT
        # =================================================
        accepted.sort(
            key=lambda item: (
                float(
                    item.result.quality_score
                ),
                int(
                    item.result.confirmations
                ),
            ),
            reverse=True,
        )
        logger.info(
            (
                "Accepted pair scan completed: "
                "%s/%s"
            ),
            len(accepted),
            len(normalized_pairs),
        )
        return accepted
# =========================================================
# EXPORTS
# =========================================================
__all__ = [
    "PairAnalysis",
    "PairSelector",
]
