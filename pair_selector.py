from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from market import (
    MarketClient,
    MarketDataError,
)

from quality_filter import (
    QualityFilter,
    QualityResult,
    analyze_timeframe,
)


logger = logging.getLogger(
    "pair_selector"
)


# ============================================================
# НАСТРОЙКИ
# ============================================================

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

DEFAULT_TIMEFRAMES = (
    "1m",
    "5m",
    "15m",
)

DEFAULT_CANDLE_LIMIT = 200

# Минимальный score для кандидата.
MIN_CANDIDATE_SCORE = 85.0

# Минимальное количество подтверждённых
# таймфреймов.
MIN_CONFIRMATIONS = 2

# Таймаут анализа одной пары.
PAIR_TIMEOUT_SECONDS = 20


# ============================================================
# PAIR ANALYSIS
# ============================================================

@dataclass(slots=True)
class PairAnalysis:

    symbol: str

    result: QualityResult

    analysis_timeframes: int = 0

    market_error: str | None = None


# ============================================================
# PAIR SELECTOR
# ============================================================

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

    # ========================================================
    # ANALYZE ONE PAIR
    # ========================================================

    async def analyze_pair(
        self,
        symbol: str,
    ) -> PairAnalysis:

        logger.info(
            "Analyzing pair %s",
            symbol,
        )

        # ----------------------------------------------------
        # Получаем данные
        # ----------------------------------------------------

        try:

            timeframe_data = (
                await asyncio.wait_for(
                    self.market.get_multi_timeframe(
                        symbol=symbol,
                        timeframes=(
                            DEFAULT_TIMEFRAMES
                        ),
                        limit=(
                            DEFAULT_CANDLE_LIMIT
                        ),
                    ),
                    timeout=(
                        PAIR_TIMEOUT_SECONDS
                    ),
                )
            )

        except asyncio.TimeoutError:

            logger.warning(
                "Timeout for %s",
                symbol,
            )

            raise MarketDataError(
                f"Timeout: {symbol}"
            )

        # ----------------------------------------------------
        # Проверяем данные
        # ----------------------------------------------------

        if not timeframe_data:

            raise MarketDataError(
                f"No timeframe data: {symbol}"
            )

        analyses = []

        # ----------------------------------------------------
        # Анализ каждого TF
        # ----------------------------------------------------

        for (
            timeframe,
            candles,
        ) in timeframe_data.items():

            try:

                result = (
                    analyze_timeframe(
                        timeframe=timeframe,
                        candles=candles,
                    )
                )

                analyses.append(
                    result
                )

            except Exception:

                logger.exception(
                    "Timeframe analysis "
                    "failed: %s %s",
                    symbol,
                    timeframe,
                )

        # ----------------------------------------------------
        # Нет анализов
        # ----------------------------------------------------

        if not analyses:

            raise MarketDataError(
                f"No valid analyses: {symbol}"
            )

        # ----------------------------------------------------
        # Quality Filter
        # ----------------------------------------------------

        quality = (
            self.quality_filter.evaluate(
                analyses
            )
        )

        logger.info(
            (
                "%s | accepted=%s "
                "score=%.2f "
                "confirmations=%s/%s"
            ),
            symbol,
            quality.accepted,
            quality.quality_score,
            quality.confirmations,
            quality.total_checks,
        )

        # ----------------------------------------------------
        # Возвращаем результат
        # ----------------------------------------------------

        return PairAnalysis(
            symbol=symbol,
            result=quality,
            analysis_timeframes=len(
                analyses
            ),
        )

    # ========================================================
    # SAFE ANALYZE
    # ========================================================

    async def _safe_analyze_pair(
        self,
        symbol: str,
    ) -> PairAnalysis | None:

        try:

            return await self.analyze_pair(
                symbol
            )

        except MarketDataError as exc:

            logger.warning(
                "%s market error: %s",
                symbol,
                exc,
            )

            return None

        except Exception:

            logger.exception(
                "Unexpected error analyzing %s",
                symbol,
            )

            return None

    # ========================================================
    # FIND BEST PAIR
    # ========================================================

    async def find_best_pair(
        self,
        pairs: list[str] | None = None,
    ) -> PairAnalysis | None:

        symbols = (
            list(pairs)
            if pairs
            else list(DEFAULT_PAIRS)
        )

        if not symbols:

            logger.warning(
                "No pairs configured."
            )

            return None

        logger.info(
            "Starting analysis of %s pairs.",
            len(symbols),
        )

        # ----------------------------------------------------
        # Анализируем пары параллельно
        # ----------------------------------------------------

        tasks = [
            self._safe_analyze_pair(
                symbol
            )
            for symbol in symbols
        ]

        results = await asyncio.gather(
            *tasks
        )

        candidates = [
            result
            for result in results
            if result is not None
        ]

        logger.info(
            "Successfully analyzed %s/%s pairs.",
            len(candidates),
            len(symbols),
        )

        # ----------------------------------------------------
        # Только принятые сигналы
        # ----------------------------------------------------

        accepted = [
            item
            for item in candidates
            if (
                item.result.accepted
                and item.result.direction
                is not None
            )
        ]

        if not accepted:

            logger.info(
                "No pair passed quality filter."
            )

            return None

        # ----------------------------------------------------
        # Дополнительный строгий фильтр
        # ----------------------------------------------------

        strong = [
            item
            for item in accepted
            if (
                item.result.quality_score
                >= MIN_CANDIDATE_SCORE
                and
                item.result.confirmations
                >= MIN_CONFIRMATIONS
            )
        ]

        if not strong:

            logger.info(
                (
                    "Pairs passed basic filter "
                    "but none passed strong filter."
                )
            )

            return None

        # ----------------------------------------------------
        # Сортировка
        # ----------------------------------------------------

        strong.sort(
            key=self._ranking_key,
            reverse=True,
        )

        best = strong[0]

        logger.info(
            (
                "BEST PAIR: %s | "
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

        return best

    # ========================================================
    # RANKING
    # ========================================================

    @staticmethod
    def _ranking_key(
        item: PairAnalysis,
    ) -> tuple:

        result = item.result

        # Сначала качество.
        #
        # Затем количество подтверждений.
        #
        # Затем процент согласия TF.
        #
        # Затем количество TF.
        #
        # Это НЕ вероятность выигрыша.
        # Это только порядок выбора кандидатов.

        if result.total_checks:

            agreement = (
                result.confirmations
                / result.total_checks
            )

        else:

            agreement = 0.0

        return (
            result.quality_score,
            agreement,
            result.confirmations,
            result.total_checks,
        )

    # ========================================================
    # ANALYZE ALL
    # ========================================================

    async def analyze_all(
        self,
        pairs: list[str] | None = None,
    ) -> list[PairAnalysis]:

        symbols = (
            list(pairs)
            if pairs
            else list(DEFAULT_PAIRS)
        )

        tasks = [
            self._safe_analyze_pair(
                symbol
            )
            for symbol in symbols
        ]

        results = await asyncio.gather(
            *tasks
        )

        return [
            result
            for result in results
            if result is not None
        ]


# ============================================================
# FACTORY
# ============================================================

def create_pair_selector(
    market: MarketClient,
    quality_filter: QualityFilter,
) -> PairSelector:

    return PairSelector(
        market=market,
        quality_filter=quality_filter,
    )
