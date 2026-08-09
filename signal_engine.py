from __future__ import annotations

from dataclasses import dataclass

from indicators import (
    calculate_indicators,
)

from market import Candle

from models import Direction


@dataclass(slots=True)
class AnalysisResult:

    direction: Direction | None

    score: float

    reasons: list[str]

    confirmations: int

    total_checks: int


class SignalEngine:

    """
    Базовый технический анализ.

    Используются:

    - EMA
    - RSI
    - MACD
    - Bollinger Bands

    Важно:

    Нейтральные индикаторы не дают
    дополнительного подтверждения.
    """

    def analyze(
        self,
        candles: list[Candle],
    ) -> AnalysisResult:

        if len(candles) < 50:

            return AnalysisResult(
                direction=None,
                score=0.0,
                reasons=[
                    "Недостаточно свечей."
                ],
                confirmations=0,
                total_checks=0,
            )

        indicators = (
            calculate_indicators(
                candles
            )
        )

        bullish = 0
        bearish = 0

        reasons: list[str] = []

        checks = 0

        # ====================================================
        # EMA
        # ====================================================

        if (
            indicators.ema_fast
            is not None
            and indicators.ema_slow
            is not None
        ):

            checks += 1

            if (
                indicators.ema_fast
                > indicators.ema_slow
            ):

                bullish += 1

                reasons.append(
                    "EMA подтверждает рост."
                )

            elif (
                indicators.ema_fast
                < indicators.ema_slow
            ):

                bearish += 1

                reasons.append(
                    "EMA подтверждает снижение."
                )

            else:

                reasons.append(
                    "EMA нейтральна."
                )

        # ====================================================
        # RSI
        # ====================================================

        if indicators.rsi is not None:

            checks += 1

            rsi = float(
                indicators.rsi
            )

            if rsi <= 30:

                bullish += 1

                reasons.append(
                    f"RSI перепродан: {rsi:.1f}."
                )

            elif rsi >= 70:

                bearish += 1

                reasons.append(
                    f"RSI перекуплен: {rsi:.1f}."
                )

            else:

                reasons.append(
                    f"RSI нейтрален: {rsi:.1f}."
                )

        # ====================================================
        # MACD
        # ====================================================

        if (
            indicators.macd
            is not None
            and indicators.macd_signal
            is not None
        ):

            checks += 1

            if (
                indicators.macd
                > indicators.macd_signal
            ):

                bullish += 1

                reasons.append(
                    "MACD подтверждает рост."
                )

            elif (
                indicators.macd
                < indicators.macd_signal
            ):

                bearish += 1

                reasons.append(
                    "MACD подтверждает снижение."
                )

            else:

                reasons.append(
                    "MACD нейтрален."
                )

        # ====================================================
        # BOLLINGER
        # ====================================================

        if (
            indicators.bollinger_upper
            is not None
            and indicators.bollinger_lower
            is not None
        ):

            checks += 1

            price = float(
                indicators.price
            )

            upper = float(
                indicators.bollinger_upper
            )

            lower = float(
                indicators.bollinger_lower
            )

            if price <= lower:

                bullish += 1

                reasons.append(
                    "Цена у нижней полосы Bollinger."
                )

            elif price >= upper:

                bearish += 1

                reasons.append(
                    "Цена у верхней полосы Bollinger."
                )

            else:

                reasons.append(
                    "Цена внутри Bollinger."
                )

        # ====================================================
        # NO CHECKS
        # ====================================================

        if checks == 0:

            return AnalysisResult(
                direction=None,
                score=0.0,
                reasons=[
                    "Индикаторы не рассчитаны."
                ],
                confirmations=0,
                total_checks=0,
            )

        # ====================================================
        # CONFLICT
        # ====================================================

        if bullish == bearish:

            return AnalysisResult(
                direction=None,
                score=0.0,
                reasons=[
                    *reasons,
                    "Нет единого направления."
                ],
                confirmations=0,
                total_checks=checks,
            )

        # ====================================================
        # UP
        # ====================================================

        if bullish > bearish:

            score = (
                bullish
                / checks
                * 100.0
            )

            return AnalysisResult(
                direction=Direction.UP,
                score=score,
                reasons=reasons,
                confirmations=bullish,
                total_checks=checks,
            )

        # ====================================================
        # DOWN
        # ====================================================

        score = (
            bearish
            / checks
            * 100.0
        )

        return AnalysisResult(
            direction=Direction.DOWN,
            score=score,
            reasons=reasons,
            confirmations=bearish,
            total_checks=checks,
        )


signal_engine = SignalEngine()
