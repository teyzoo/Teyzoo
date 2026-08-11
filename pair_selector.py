from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Iterable

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

    @property
    def accepted(self) -> bool:
        return self.result.accepted

    @property
    def direction(self):
        return self.result.direction

    @property
    def quality_score(self) -> float:
        return float(
            self.result.quality_score
        )

    @property
    def confirmations(self) -> int:
        return int(
            self.result.confirmations
        )

    @property
    def total_checks(self) -> int:
        return int(
            self.result.total_checks
        )


class PairSelector:

    def __init__(
        self,
        market: MarketClient,
        quality_filter: QualityFilter,
        max_concurrent_pairs: int = 2,
    ) -> None:
        self.market = market
        self.quality_filter = quality_filter

        self.max_concurrent_pairs = max(
            1,
            int(max_concurrent_pairs),
        )

        self._semaphore = asyncio.Semaphore(
            self.max_concurrent_pairs
        )

    @staticmethod
    def _normalize_symbol(
        symbol: str,
    ) -> str:
        value = (
            str(symbol)
            .strip()
            .upper()
        )

        if not value:
            raise ValueError(
                "Empty trading pair."
            )

        if (
            "/" not in value
            and len(value) == 6
            and value.isalpha()
        ):
            value = (
                value[:3]
                + "/"
                + value[3:]
            )

        return value

    @classmethod
    def _normalize_pairs(
        cls,
        pairs: Iterable[str],
    ) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()

        for pair in pairs:
            try:
                symbol = cls._normalize_symbol(
                    pair
                )
            except ValueError:
                continue

            if symbol in seen:
                continue

            seen.add(symbol)
            result.append(symbol)

        return result

    async def _analyze_timeframe(
        self,
        symbol: str,
        timeframe: str,
    ):
        try:
            candles = (
                await self.market.get_candles(
                    symbol=symbol,
                    timeframe=timeframe,
                    limit=MARKET_CANDLE_LIMIT,
                )
            )
        except Exception as exc:
            logger.warning(
                "%s | %s | candle loading failed: %s",
                symbol,
                timeframe,
                exc,
            )
            return None

        if len(candles) < 20:
            return None

        try:
            return analyze_timeframe(
                timeframe,
                candles,
            )
        except Exception:
            logger.exception(
                "%s | %s | analysis failed",
                symbol,
                timeframe,
            )
            return None

    async def analyze_pair(
        self,
        symbol: str,
    ) -> PairAnalysis:
        symbol = self._normalize_symbol(
            symbol
        )

        analyses = []

        for timeframe in TIMEFRAMES:
            result = await self._analyze_timeframe(
                symbol,
                timeframe,
            )

            if result is not None:
                analyses.append(result)

        if not analyses:
            raise RuntimeError(
                f"No timeframe analyses for {symbol}"
            )

        quality = self.quality_filter.evaluate(
            analyses
        )

        return PairAnalysis(
            symbol=symbol,
            result=quality,
        )

    async def _safe_analyze_pair(
        self,
        symbol: str,
    ) -> PairAnalysis | None:
        async with self._semaphore:
            try:
                return await self.analyze_pair(
                    symbol
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Pair analysis failed: %s",
                    symbol,
                )
                return None

    @staticmethod
    def _ranking_key(
        analysis: PairAnalysis,
    ) -> tuple:
        result = analysis.result

        total = max(
            1,
            result.total_checks,
        )

        agreement = (
            result.confirmations
            / total
        )

        selected_scores = [
            item.score
            for item
            in result.timeframe_results
            if (
                item.direction is not None
                and item.direction
                == result.direction
            )
        ]

        average_score = (
            sum(selected_scores)
            / len(selected_scores)
            if selected_scores
            else 0.0
        )

        return (
            int(result.accepted),
            float(result.quality_score),
            int(result.confirmations),
            float(agreement),
            float(average_score),
        )

    async def find_best_pair(
        self,
        pairs: list[str] | None = None,
    ) -> PairAnalysis | None:
        selected = (
            DEFAULT_PAIRS
            if pairs is None
            else pairs
        )

        normalized = self._normalize_pairs(
            selected
        )

        if not normalized:
            return None

        tasks = [
            asyncio.create_task(
                self._safe_analyze_pair(
                    symbol
                )
            )
            for symbol in normalized
        ]

        results = await asyncio.gather(
            *tasks
        )

        accepted = [
            result
            for result in results
            if (
                result is not None
                and result.result.accepted
                and result.result.direction is not None
            )
        ]

        if not accepted:
            return None

        accepted.sort(
            key=self._ranking_key,
            reverse=True,
        )

        return accepted[0]

    async def find_accepted_pairs(
        self,
        pairs: list[str] | None = None,
    ) -> list[PairAnalysis]:
        selected = (
            DEFAULT_PAIRS
            if pairs is None
            else pairs
        )

        normalized = self._normalize_pairs(
            selected
        )

        if not normalized:
            return []

        tasks = [
            asyncio.create_task(
                self._safe_analyze_pair(
                    symbol
                )
            )
            for symbol in normalized
        ]

        results = await asyncio.gather(
            *tasks
        )

        accepted = [
            result
            for result in results
            if (
                result is not None
                and result.result.accepted
                and result.result.direction is not None
            )
        ]

        accepted.sort(
            key=self._ranking_key,
            reverse=True,
        )

        return accepted


def create_pair_selector(
    market: MarketClient,
    quality_filter: QualityFilter,
) -> PairSelector:
    return PairSelector(
        market=market,
        quality_filter=quality_filter,
        max_concurrent_pairs=2,
    )


__all__ = [
    "PairAnalysis",
    "PairSelector",
    "create_pair_selector",
]
