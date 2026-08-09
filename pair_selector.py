from __future__ import annotations

from dataclasses import dataclass

from market import MarketClient
from quality_filter import (
    QualityFilter,
    QualityResult,
)


DEFAULT_PAIRS = [
    "EUR/USD",
    "GBP/USD",
    "USD/JPY",
    "USD/CHF",
    "AUD/USD",
    "USD/CAD",
    "NZD/USD",
    "EUR/GBP",
    "EUR/JPY",
    "GBP/JPY",
]


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
        self.quality_filter = (
            quality_filter
        )

    async def analyze_pair(
        self,
        symbol: str,
    ) -> PairAnalysis:

        timeframe_data = (
            await self.market.get_multi_timeframe(
                symbol=symbol,
                timeframes=(
                    "1m",
                    "5m",
                    "15m",
                ),
                limit=200,
            )
        )

        from quality_filter import (
            analyze_timeframe,
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

        quality = (
            self.quality_filter.evaluate(
                analyses
            )
        )

        return PairAnalysis(
            symbol=symbol,
            result=quality,
        )

    async def find_best_pair(
        self,
        pairs: list[str] | None = None,
    ) -> PairAnalysis | None:

        pairs = pairs or DEFAULT_PAIRS

        candidates: list[PairAnalysis] = []

        for symbol in pairs:

            try:

                analysis = (
                    await self.analyze_pair(
                        symbol
                    )
                )

                candidates.append(
                    analysis
                )

            except Exception:
                continue

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
