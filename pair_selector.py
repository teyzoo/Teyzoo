from __future__ import annotations

import asyncio
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

    - анализировать пары;
    - получать данные сразу по нескольким таймфреймам;
    - применять QualityFilter;
    - переживать HTTP 429;
    - не останавливать весь сканер из-за одной пары;
    - не делать лишние запросы;
    - возвращать лучшую принятую пару.
    """

    def __init__(
        self,
        market: MarketClient,
        quality_filter: QualityFilter,
    ) -> None:
        self.market = market
        self.quality_filter = quality_filter

        # -------------------------------------------------
        # Защита от слишком частого запуска анализа.
        #
        # Scheduler у тебя запускает анализ примерно
        # каждые 20 секунд.
        #
        # Если предыдущий анализ ещё идёт,
        # второй одновременно не запускаем.
        # -------------------------------------------------

        self._analysis_lock = asyncio.Lock()

    # =====================================================
    # ANALYZE ONE PAIR
    # =====================================================

    async def analyze_pair(
        self,
        symbol: str,
    ) -> PairAnalysis:
        """
        Анализ одной пары.

        Если Twelve Data временно ограничил запросы,
        MarketRateLimitError пробрасывается выше,
        чтобы find_best_pair() мог корректно остановить
        текущий цикл вместо генерации десятков ошибок.
        """

        symbol = str(symbol).strip().upper()

        if not symbol:
            raise ValueError(
                "Pair symbol is empty."
            )

        logger.info(
            "Analyzing pair: %s",
            symbol,
        )

        # =================================================
        # LOAD MULTI-TIMEFRAME DATA
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
            logger.warning(
                "Rate limit reached while analyzing %s. "
                "Stopping current pair scan.",
                symbol,
            )

            raise

        except MarketDataError as exc:
            logger.warning(
                "Market data error for %s: %s",
                symbol,
                exc,
            )

            raise

        except Exception:
            logger.exception(
                "Unexpected market error for %s.",
                symbol,
            )

            raise

        # =================================================
        # NO DATA
        # =================================================

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

            if not candles:
                logger.warning(
                    "%s | %s | no candles.",
                    symbol,
                    timeframe,
                )

                continue

            # -------------------------------------------------
            # Проверяем минимальное количество свечей.
            #
            # MARKET_CANDLE_LIMIT обычно 200.
            # Но здесь не требуем строго 200, потому что
            # provider сам валидирует минимум 20.
            # -------------------------------------------------

            if candle_count < 20:
                logger.warning(
                    "%s | %s | insufficient candles=%s.",
                    symbol,
                    timeframe,
                    candle_count,
                )

                continue

            try:
                result = analyze_timeframe(
                    timeframe,
                    candles,
                )

            except Exception:
                logger.exception(
                    "%s | %s | "
                    "timeframe analysis failed.",
                    symbol,
                    timeframe,
                )

                continue

            analyses.append(
                result
            )

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
                "%s: QualityFilter failed.",
                symbol,
            )

            raise

        # =================================================
        # LOG RESULT
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
        Анализирует список пар и возвращает лучшую.

        Важная защита:

        Если Twelve Data возвращает 429,
        текущий цикл немедленно прекращается.

        Это предотвращает ситуацию:

            EUR/USD -> 429
            GBP/USD -> 429
            USD/JPY -> 429
            USD/CHF -> 429
            ...

        и дальнейшее бессмысленное ожидание.

        Следующий запуск scheduler уже попробует
        продолжить работу после cooldown.
        """

        # =================================================
        # PREVENT OVERLAPPING SCANS
        # =================================================

        if self._analysis_lock.locked():
            logger.warning(
                "Pair selection is already running. "
                "Skipping overlapping scan."
            )

            return None

        async with self._analysis_lock:

            # =================================================
            # SELECT PAIRS
            # =================================================

            selected_pairs = (
                list(pairs)
                if pairs is not None
                else list(DEFAULT_PAIRS)
            )

            # Удаляем пустые значения и дубликаты.
            normalized_pairs: list[str] = []

            seen: set[str] = set()

            for pair in selected_pairs:
                symbol = (
                    str(pair)
                    .strip()
                    .upper()
                )

                if not symbol:
                    continue

                if symbol in seen:
                    continue

                seen.add(symbol)

                normalized_pairs.append(
                    symbol
                )

            selected_pairs = normalized_pairs

            if not selected_pairs:
                logger.warning(
                    "No pairs configured for selection."
                )

                return None

            logger.info(
                "Starting pair selection. "
                "Pairs=%s",
                len(selected_pairs),
            )

            # =================================================
            # CANDIDATES
            # =================================================

            candidates: list[PairAnalysis] = []

            # =================================================
            # ANALYZE PAIRS SEQUENTIALLY
            # =================================================

            for index, symbol in enumerate(
                selected_pairs,
                start=1,
            ):
                logger.info(
                    "Pair scan progress: %s/%s | %s",
                    index,
                    len(selected_pairs),
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

                except MarketRateLimitError as exc:
                    logger.warning(
                        (
                            "Twelve Data rate limit "
                            "reached while scanning %s. "
                            "Stopping current scan. "
                            "Already analyzed=%s/%s. "
                            "Error=%s"
                        ),
                        symbol,
                        index - 1,
                        len(selected_pairs),
                        exc,
                    )

                    # Очень важно:
                    #
                    # НЕ продолжаем цикл.
                    #
                    # Иначе остальные пары будут
                    # создавать новые попытки после 429.
                    #
                    break

                # -------------------------------------------------
                # MARKET ERROR
                # -------------------------------------------------

                except MarketDataError as exc:
                    logger.warning(
                        "Pair analysis skipped: %s | %s",
                        symbol,
                        exc,
                    )

                    continue

                # -------------------------------------------------
                # VALUE ERROR
                # -------------------------------------------------

                except ValueError as exc:
                    logger.warning(
                        "Invalid pair %s: %s",
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
                # ADD CANDIDATE
                # =================================================

                candidates.append(
                    analysis
                )

                logger.info(
                    (
                        "Pair candidate added: "
                        "%s | score=%.2f | "
                        "accepted=%s"
                    ),
                    analysis.symbol,
                    analysis.result.quality_score,
                    analysis.result.accepted,
                )

            # =================================================
            # SCAN COMPLETE
            # =================================================

            logger.info(
                (
                    "Pair analysis completed. "
                    "Candidates=%s/%s"
                ),
                len(candidates),
                len(selected_pairs),
            )

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
            # NOTHING ACCEPTED
            # =================================================

            if not accepted:
                logger.info(
                    "No pair passed Quality Filter."
                )

                return None

            # =================================================
            # SORT
            # =================================================
            #
            # Сначала score.
            #
            # Если score одинаковый,
            # больше confirmations выигрывает.
            #
            # =================================================

            accepted.sort(
                key=lambda item: (
                    item.result.quality_score,
                    item.result.confirmations,
                ),
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
