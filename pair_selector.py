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
    MarketClient,
    MarketDataError,
    MarketRateLimitError,
)
from quality_filter import (
    QualityFilter,
    QualityResult,
    TimeframeAnalysis,
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
        Символ пары.

    result:
        Финальный результат QualityFilter.
    """

    symbol: str
    result: QualityResult


# =========================================================
# PAIR SELECTOR
# =========================================================


class PairSelector:
    """
    Выбирает лучшую торговую пару среди доступных.

    Архитектура:

        PairSelector
             |
             v
        MarketClient
             |
             v
        get_multi_timeframe()
             |
             v
        candles по каждому TF
             |
             v
        analyze_timeframe()
             |
             v
        QualityFilter
             |
             v
        PairAnalysis

    Важно:

    PairSelector НЕ делает собственных HTTP-запросов.

    Все запросы идут через MarketClient, поэтому:

    - cache MarketClient работает;
    - request deduplication работает;
    - rate limit работает;
    - stale cache работает;
    - Twelve Data не вызывается напрямую.
    """

    def __init__(
        self,
        market: MarketClient,
        quality_filter: QualityFilter,
    ) -> None:
        self.market = market
        self.quality_filter = quality_filter

    # =====================================================
    # ANALYZE PAIR
    # =====================================================

    async def analyze_pair(
        self,
        symbol: str,
    ) -> PairAnalysis:
        """
        Полностью анализирует одну пару.

        Например:

            EUR/USD

        будет проверен по всем TIMEFRAMES из config.py.
        """

        symbol = str(symbol).strip().upper()

        if not symbol:
            raise ValueError(
                "Symbol is required."
            )

        logger.info(
            "================================================"
        )

        logger.info(
            "Analyzing pair: %s",
            symbol,
        )

        logger.info(
            "Timeframes: %s",
            TIMEFRAMES,
        )

        logger.info(
            "Candle limit: %s",
            MARKET_CANDLE_LIMIT,
        )

        # =================================================
        # LOAD MULTI-TIMEFRAME DATA
        # =================================================

        try:
            timeframe_data = (
                await self.market.get_multi_timeframe(
                    symbol=symbol,
                    timeframes=tuple(TIMEFRAMES),
                    limit=MARKET_CANDLE_LIMIT,
                )
            )

        except MarketRateLimitError:
            logger.warning(
                "%s: market API rate limit reached.",
                symbol,
            )
            raise

        except MarketDataError:
            logger.exception(
                "%s: market data error.",
                symbol,
            )
            raise

        except Exception:
            logger.exception(
                "%s: unexpected market error.",
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

            raise RuntimeError(
                f"No timeframe data for {symbol}"
            )

        logger.info(
            "%s: received %s timeframe(s).",
            symbol,
            len(timeframe_data),
        )

        # =================================================
        # ANALYZE EACH TIMEFRAME
        # =================================================

        analyses: list[
            TimeframeAnalysis
        ] = []

        for timeframe in TIMEFRAMES:

            candles = timeframe_data.get(
                timeframe
            )

            candle_count = (
                len(candles)
                if candles
                else 0
            )

            logger.info(
                (
                    "%s | %s | "
                    "candles=%s"
                ),
                symbol,
                timeframe,
                candle_count,
            )

            # -------------------------------------------------
            # No candles
            # -------------------------------------------------

            if not candles:
                logger.warning(
                    (
                        "%s | %s | "
                        "no candles available."
                    ),
                    symbol,
                    timeframe,
                )

                continue

            # -------------------------------------------------
            # Analyze timeframe
            # -------------------------------------------------

            try:
                result = analyze_timeframe(
                    timeframe=timeframe,
                    candles=candles,
                )

            except Exception:
                logger.exception(
                    (
                        "%s | %s | "
                        "timeframe analysis failed."
                    ),
                    symbol,
                    timeframe,
                )

                continue

            analyses.append(
                result
            )

            logger.info(
                (
                    "%s | %s | "
                    "direction=%s | "
                    "score=%.2f | "
                    "reasons=%s"
                ),
                symbol,
                timeframe,
                result.direction,
                result.score,
                result.reasons,
            )

        # =================================================
        # NO ANALYSES
        # =================================================

        if not analyses:
            logger.warning(
                (
                    "%s: "
                    "no timeframe analyses produced."
                ),
                symbol,
            )

            raise RuntimeError(
                f"No timeframe analyses for {symbol}"
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
                (
                    "%s: "
                    "QualityFilter evaluation failed."
                ),
                symbol,
            )

            raise

        # =================================================
        # LOG QUALITY RESULT
        # =================================================

        logger.info(
            (
                "%s | Quality Filter | "
                "accepted=%s | "
                "score=%.2f | "
                "confirmations=%s/%s | "
                "direction=%s"
            ),
            symbol,
            quality.accepted,
            quality.quality_score,
            quality.confirmations,
            quality.total_checks,
            quality.direction,
        )

        if quality.reasons:
            logger.info(
                "%s | Quality reasons: %s",
                symbol,
                quality.reasons,
            )

        if quality.rejected_reasons:
            logger.info(
                "%s | Rejected reasons: %s",
                symbol,
                quality.rejected_reasons,
            )

        # =================================================
        # FINAL
        # =================================================

        logger.info(
            "Finished pair analysis: %s",
            symbol,
        )

        logger.info(
            "================================================"
        )

        return PairAnalysis(
            symbol=symbol,
            result=quality,
        )

    # =====================================================
    # ANALYZE MANY PAIRS
    # =====================================================

    async def analyze_pairs(
        self,
        pairs: Iterable[str],
    ) -> list[PairAnalysis]:
        """
        Анализирует несколько пар.

        Ошибка одной пары не ломает анализ остальных.
        """

        selected_pairs: list[str] = []

        for symbol in pairs:
            normalized = (
                str(symbol)
                .strip()
                .upper()
            )

            if not normalized:
                continue

            if normalized in selected_pairs:
                continue

            selected_pairs.append(
                normalized
            )

        if not selected_pairs:
            logger.warning(
                "No valid pairs supplied."
            )
            return []

        logger.info(
            (
                "Starting analysis of "
                "%s pair(s)."
            ),
            len(selected_pairs),
        )

        candidates: list[
            PairAnalysis
        ] = []

        for symbol in selected_pairs:

            try:
                analysis = (
                    await self.analyze_pair(
                        symbol
                    )
                )

            except MarketRateLimitError:
                logger.warning(
                    (
                        "Rate limit reached "
                        "while analyzing %s."
                    ),
                    symbol,
                )

                # Не продолжаем бессмысленно
                # долбить API после 429.
                break

            except Exception:
                logger.exception(
                    (
                        "Pair analysis failed: "
                        "%s"
                    ),
                    symbol,
                )

                continue

            candidates.append(
                analysis
            )

        logger.info(
            (
                "Pair analysis completed. "
                "Candidates=%s/%s"
            ),
            len(candidates),
            len(selected_pairs),
        )

        return candidates

    # =====================================================
    # FIND BEST PAIR
    # =====================================================

    async def find_best_pair(
        self,
        pairs: list[str] | None = None,
    ) -> PairAnalysis | None:
        """
        Анализирует пары и выбирает лучший принятый результат.

        Если pairs=None:

            DEFAULT_PAIRS

        из config.py.

        Критерии сортировки:

        1. quality_score
        2. confirmations
        3. total_checks
        """

        if pairs is None:
            selected_pairs = list(
                DEFAULT_PAIRS
            )
        else:
            selected_pairs = list(
                pairs
            )

        # =================================================
        # NORMALIZE
        # =================================================

        normalized_pairs: list[str] = []

        for symbol in selected_pairs:
            normalized = (
                str(symbol)
                .strip()
                .upper()
            )

            if not normalized:
                continue

            if normalized in normalized_pairs:
                continue

            normalized_pairs.append(
                normalized
            )

        if not normalized_pairs:
            logger.warning(
                "No pairs available for selection."
            )
            return None

        logger.info(
            "================================================"
        )

        logger.info(
            (
                "Starting pair selection. "
                "Pairs=%s"
            ),
            len(normalized_pairs),
        )

        logger.info(
            "Pairs: %s",
            normalized_pairs,
        )

        # =================================================
        # ANALYZE
        # =================================================

        candidates = (
            await self.analyze_pairs(
                normalized_pairs
            )
        )

        if not candidates:
            logger.info(
                "No pair analyses completed."
            )
            return None

        # =================================================
        # ACCEPTED
        # =================================================

        accepted = [
            item
            for item in candidates
            if item.result.accepted
            and item.result.direction is not None
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
        # NO ACCEPTED
        # =================================================

        if not accepted:
            logger.info(
                "No pair passed Quality Filter."
            )

            logger.info(
                "================================================"
            )

            return None

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
                int(
                    item.result.total_checks
                ),
            ),
            reverse=True,
        )

        # =================================================
        # BEST
        # =================================================

        best = accepted[0]

        logger.info(
            (
                "BEST PAIR SELECTED | "
                "symbol=%s | "
                "direction=%s | "
                "quality=%.2f | "
                "confirmations=%s/%s"
            ),
            best.symbol,
            best.result.direction,
            best.result.quality_score,
            best.result.confirmations,
            best.result.total_checks,
        )

        logger.info(
            "================================================"
        )

        return best


# =========================================================
# DEFAULT FACTORY
# =========================================================


def create_pair_selector(
    market: MarketClient,
    quality_filter: QualityFilter,
) -> PairSelector:
    """
    Удобная фабрика.

    Использование:

        selector = create_pair_selector(
            market=market,
            quality_filter=quality_filter,
        )
    """

    return PairSelector(
        market=market,
        quality_filter=quality_filter,
    )


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "PairAnalysis",
    "PairSelector",
    "create_pair_selector",
]
