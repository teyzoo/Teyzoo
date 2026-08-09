from __future__ import annotations
import logging
from dataclasses import dataclass
from config import (
    DEFAULT_PAIRS,
    MARKET_CANDLE_LIMIT,
    TIMEFRAMES,
)
from market import MarketClient
from quality_filter import (
    QualityFilter,
    QualityResult,
    analyze_timeframe,
)
logger = logging.getLogger(
    "pair_selector"
)
@dataclass(slots=True)
class PairAnalysis:
    symbol: str
    result: QualityResult
class PairSelector:
    def __init__(
        self,
        market: MarketClient,
        quality_filter: QualityFilter,
    ):
        self.market = market
        self.quality_filter = quality_filter
    async def analyze_pair(
        self,
        symbol: str,
    ) -> PairAnalysis:
        logger.info(
            "Analyzing pair: %s",
            symbol,
        )
        timeframe_data = (
            await self.market.get_multi_timeframe(
                symbol=symbol,
                timeframes=TIMEFRAMES,
                limit=MARKET_CANDLE_LIMIT,
            )
        )
        if not timeframe_data:
            logger.warning(
                "%s: no timeframe data received.",
                symbol,
            )
        analyses = []
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
            try:
                result = analyze_timeframe(
                    timeframe,
                    candles,
                )
                analyses.append(result)
            except Exception:
                logger.exception(
                    "%s | %s | timeframe analysis failed.",
                    symbol,
                    timeframe,
                )
        if not analyses:
            logger.warning(
                "%s: no timeframe analyses produced.",
                symbol,
            )
            raise RuntimeError(
                f"No timeframe analyses for {symbol}"
            )
        quality = self.quality_filter.evaluate(
            analyses
        )
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
    async def find_best_pair(
        self,
        pairs: list[str] | None = None,
    ) -> PairAnalysis | None:
        selected_pairs = (
            pairs
            if pairs is not None
            else DEFAULT_PAIRS
        )
        logger.info(
            "Starting pair selection. "
            "Pairs=%s",
            len(selected_pairs),
        )
        candidates: list[PairAnalysis] = []
        for symbol in selected_pairs:
            try:
                analysis = await self.analyze_pair(
                    symbol
                )
            except Exception:
                logger.exception(
                    "Pair analysis failed: %s",
                    symbol,
                )
                continue
            candidates.append(
                analysis
            )
        logger.info(
            "Pair analysis completed. "
            "Candidates=%s",
            len(candidates),
        )
        accepted = [
            item
            for item in candidates
            if item.result.accepted
        ]
        logger.info(
            "Quality Filter accepted "
            "%s/%s pairs.",
            len(accepted),
            len(candidates),
        )
        if not accepted:
            logger.info(
                "No pair passed Quality Filter."
            )
            return None
        accepted.sort(
            key=lambda item: (
                item.result.quality_score,
                item.result.confirmations,
            ),
            reverse=True,
        )
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
