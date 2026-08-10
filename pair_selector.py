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


logger = logging.getLogger("pair_selector")


# =========================================================
# DATA MODEL
# =========================================================


@dataclass(slots=True)
class PairAnalysis:
    symbol: str
    result: QualityResult

    @property
    def accepted(self) -> bool:
        return bool(self.result.accepted)

    @property
    def direction(self):
        return self.result.direction

    @property
    def quality_score(self) -> float:
        return float(self.result.quality_score)

    @property
    def confirmations(self) -> int:
        return int(self.result.confirmations)

    @property
    def total_checks(self) -> int:
        return int(self.result.total_checks)


# =========================================================
# PAIR SELECTOR
# =========================================================


class PairSelector:
    """
    Выбирает лучшую валютную пару для сигнала.

    Основная схема:

        pair
          ↓
        MarketClient
          ↓
        несколько таймфреймов
          ↓
        SignalEngine
          ↓
        QualityFilter
          ↓
        PairAnalysis
          ↓
        ranking
          ↓
        best pair

    Важные свойства:

    - совместим с текущим MarketClient;
    - не падает из-за одной плохой пары;
    - не падает из-за одного плохого TF;
    - умеет ограничивать параллельные запросы;
    - удаляет дубликаты пар;
    - нормализует названия;
    - ранжирует сигналы;
    - не выдаёт неподтверждённые пары.
    """

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

        self._pair_semaphore = asyncio.Semaphore(
            self.max_concurrent_pairs
        )

    # =====================================================
    # NORMALIZE PAIR
    # =====================================================

    @staticmethod
    def _normalize_symbol(
        symbol: str,
    ) -> str:
        value = str(symbol).strip().upper()

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
                f"{value[:3]}/{value[3:]}"
            )

        return value

    # =====================================================
    # NORMALIZE PAIRS
    # =====================================================

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
            except Exception:
                continue

            if symbol in seen:
                continue

            seen.add(symbol)
            result.append(symbol)

        return result

    # =====================================================
    # ANALYZE TIMEFRAME
    # =====================================================

    async def _analyze_timeframe(
        self,
        symbol: str,
        timeframe: str,
    ):
        """
        Загружает свечи одного TF и анализирует их.

        Ошибка одного TF не ломает всю пару.
        """

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

        if not candles:
            logger.warning(
                "%s | %s | empty candles.",
                symbol,
                timeframe,
            )
            return None

        if len(candles) < 20:
            logger.warning(
                (
                    "%s | %s | insufficient candles: "
                    "%s"
                ),
                symbol,
                timeframe,
                len(candles),
            )
            return None

        logger.info(
            "%s | %s | candles=%s",
            symbol,
            timeframe,
            len(candles),
        )

        try:
            result = analyze_timeframe(
                timeframe,
                candles,
            )

        except Exception as exc:
            logger.exception(
                (
                    "%s | %s | timeframe "
                    "analysis failed: %s"
                ),
                symbol,
                timeframe,
                exc,
            )
            return None

        return result

    # =====================================================
    # ANALYZE PAIR
    # =====================================================

    async def analyze_pair(
        self,
        symbol: str,
    ) -> PairAnalysis:
        symbol = self._normalize_symbol(
            symbol
        )

        logger.info(
            "================================================"
        )
        logger.info(
            "Analyzing pair: %s",
            symbol,
        )
        logger.info(
            "================================================"
        )

        analyses = []

        # -------------------------------------------------
        # Таймфреймы анализируем последовательно.
        #
        # Это специально.
        #
        # MarketClient уже защищён от лишних запросов
        # cache + request lock + rate limiter.
        #
        # Но последовательный запрос TF дополнительно
        # защищает Twelve Data от лишней нагрузки.
        # -------------------------------------------------

        for timeframe in TIMEFRAMES:
            result = await self._analyze_timeframe(
                symbol=symbol,
                timeframe=timeframe,
            )

            if result is not None:
                analyses.append(
                    result
                )

        # =================================================
        # NO ANALYSIS
        # =================================================

        if not analyses:
            logger.warning(
                "%s: no timeframe analyses produced.",
                symbol,
            )

            raise RuntimeError(
                f"No timeframe analyses for {symbol}"
            )

        # =================================================
        # QUALITY FILTER
        # =================================================

        quality = self.quality_filter.evaluate(
            analyses
        )

        logger.info(
            (
                "%s | QUALITY | "
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

        if quality.rejected_reasons:
            logger.info(
                "%s | REJECTED REASONS: %s",
                symbol,
                quality.rejected_reasons,
            )

        return PairAnalysis(
            symbol=symbol,
            result=quality,
        )

    # =====================================================
    # SAFE ANALYZE PAIR
    # =====================================================

    async def _safe_analyze_pair(
        self,
        symbol: str,
    ) -> PairAnalysis | None:
        async with self._pair_semaphore:
            try:
                return await self.analyze_pair(
                    symbol
                )

            except asyncio.CancelledError:
                raise

            except Exception as exc:
                logger.exception(
                    "Pair analysis failed: %s: %s",
                    symbol,
                    exc,
                )
                return None

    # =====================================================
    # RANK KEY
    # =====================================================

    @staticmethod
    def _ranking_key(
        analysis: PairAnalysis,
    ) -> tuple:
        """
        Главный ranking.

        Приоритет:

        1. accepted
        2. quality score
        3. confirmations
        4. agreement ratio
        5. средний score подтверждающих TF
        """

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
            for item in result.timeframe_results
            if (
                item.direction is not None
                and item.direction
                == result.direction
            )
        ]

        if selected_scores:
            average_tf_score = (
                sum(selected_scores)
                / len(selected_scores)
            )
        else:
            average_tf_score = 0.0

        return (
            int(result.accepted),
            float(result.quality_score),
            int(result.confirmations),
            float(agreement),
            float(average_tf_score),
        )

    # =====================================================
    # FIND BEST PAIR
    # =====================================================

    async def find_best_pair(
        self,
        pairs: list[str] | None = None,
    ) -> PairAnalysis | None:
        selected_pairs = (
            pairs
            if pairs is not None
            else DEFAULT_PAIRS
        )

        normalized_pairs = (
            self._normalize_pairs(
                selected_pairs
            )
        )

        if not normalized_pairs:
            logger.warning(
                "No valid trading pairs supplied."
            )
            return None

        logger.info(
            "================================================"
        )
        logger.info(
            "PAIR SELECTION STARTED"
        )
        logger.info(
            "Pairs=%s",
            len(normalized_pairs),
        )
        logger.info(
            "Timeframes=%s",
            TIMEFRAMES,
        )
        logger.info(
            "Candle limit=%s",
            MARKET_CANDLE_LIMIT,
        )
        logger.info(
            "Concurrency=%s",
            self.max_concurrent_pairs,
        )
        logger.info(
            "================================================"
        )

        # =================================================
        # ANALYZE PAIRS
        # =================================================

        tasks = [
            asyncio.create_task(
                self._safe_analyze_pair(
                    symbol
                )
            )
            for symbol in normalized_pairs
        ]

        raw_results = await asyncio.gather(
            *tasks
        )

        candidates = [
            result
            for result in raw_results
            if result is not None
        ]

        logger.info(
            "Pair analysis completed: %s/%s.",
            len(candidates),
            len(normalized_pairs),
        )

        # =================================================
        # NO CANDIDATES
        # =================================================

        if not candidates:
            logger.warning(
                "No pair analysis candidates."
            )
            return None

        # =================================================
        # PRINT SUMMARY
        # =================================================

        for item in candidates:
            result = item.result

            logger.info(
                (
                    "PAIR RESULT | "
                    "%s | "
                    "accepted=%s | "
                    "direction=%s | "
                    "quality=%.2f | "
                    "confirmations=%s/%s"
                ),
                item.symbol,
                result.accepted,
                result.direction,
                result.quality_score,
                result.confirmations,
                result.total_checks,
            )

        # =================================================
        # ACCEPTED ONLY
        # =================================================

        accepted = [
            item
            for item in candidates
            if item.result.accepted
            and item.result.direction is not None
        ]

        logger.info(
            "Quality accepted: %s/%s.",
            len(accepted),
            len(candidates),
        )

        if not accepted:
            logger.info(
                "No pair passed Quality Filter."
            )
            return None

        # =================================================
        # SORT
        # =================================================

        accepted.sort(
            key=self._ranking_key,
            reverse=True,
        )

        best = accepted[0]

        # =================================================
        # LOG RANKING
        # =================================================

        logger.info(
            "================================================"
        )
        logger.info(
            "BEST PAIR SELECTED"
        )
        logger.info(
            "Symbol=%s",
            best.symbol,
        )
        logger.info(
            "Direction=%s",
            best.result.direction,
        )
        logger.info(
            "Quality=%.2f",
            best.result.quality_score,
        )
        logger.info(
            "Confirmations=%s/%s",
            best.result.confirmations,
            best.result.total_checks,
        )
        logger.info(
            "Reasons=%s",
            best.result.reasons,
        )
        logger.info(
            "================================================"
        )

        return best

    # =====================================================
    # FIND ALL ACCEPTED
    # =====================================================

    async def find_accepted_pairs(
        self,
        pairs: list[str] | None = None,
    ) -> list[PairAnalysis]:
        """
        Возвращает все пары, которые прошли фильтр.

        Полезно для SignalScanner, если позже захочешь
        выдавать несколько лучших сигналов.
        """

        selected_pairs = (
            pairs
            if pairs is not None
            else DEFAULT_PAIRS
        )

        normalized_pairs = (
            self._normalize_pairs(
                selected_pairs
            )
        )

        if not normalized_pairs:
            return []

        tasks = [
            asyncio.create_task(
                self._safe_analyze_pair(
                    symbol
                )
            )
            for symbol in normalized_pairs
        ]

        raw_results = await asyncio.gather(
            *tasks
        )

        accepted = [
            item
            for item in raw_results
            if (
                item is not None
                and item.result.accepted
                and item.result.direction
                is not None
            )
        ]

        accepted.sort(
            key=self._ranking_key,
            reverse=True,
        )

        return accepted


# =========================================================
# DEFAULT FACTORY
# =========================================================


def create_pair_selector(
    market: MarketClient,
    quality_filter: QualityFilter,
) -> PairSelector:
    return PairSelector(
        market=market,
        quality_filter=quality_filter,
        max_concurrent_pairs=2,
    )


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "PairAnalysis",
    "PairSelector",
    "create_pair_selector",
]
