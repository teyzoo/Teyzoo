from __future__ import annotations

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

        timeframe_data = (
            await self.market.get_multi_timeframe(
                symbol=symbol,
                timeframes=TIMEFRAMES,
                limit=MARKET_CANDLE_LIMIT,
            )
        )

        analyses = []

        for timeframe, candles in (
            timeframe_data.items()
        ):
            result = analyze_timeframe(
                timeframe,
                candles,
            )

            analyses.append(result)

        quality = self.quality_filter.evaluate(
            analyses
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

        candidates: list[PairAnalysis] = []

        for symbol in selected_pairs:
            try:
                analysis = await self.analyze_pair(
                    symbol
                )
            except Exception:
                continue

            candidates.append(analysis)

        accepted = [
            item
            for item in candidates
            if item.result.accepted
        ]

        if not accepted:
            return None

        accepted.sort(
            key=lambda item: (
                item.result.quality_score,
                item.result.confirmations,
            ),
            reverse=True,
        )

        return accepted[0]
