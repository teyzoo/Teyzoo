from __future__ import annotations

from dataclasses import dataclass

from indicators import calculate_indicators
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

        if indicators.rsi is not None:

            checks += 1

            if indicators.rsi < 35:

                bullish += 1

                reasons.append(
                    "RSI показывает "
                    "перепроданность."
                )

            elif indicators.rsi > 65:

                bearish += 1

                reasons.append(
                    "RSI показывает "
                    "перекупленность."
                )

        if (
            indicators.macd is not None
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

        if (
            indicators.bollinger_upper
            is not None
            and indicators.bollinger_lower
            is not None
        ):

            checks += 1

            if (
                indicators.price
                <= indicators.bollinger_lower
            ):

                bullish += 1

                reasons.append(
                    "Цена возле нижней "
                    "границы Bollinger."
                )

            elif (
                indicators.price
                >= indicators.bollinger_upper
            ):

                bearish += 1

                reasons.append(
                    "Цена возле верхней "
                    "границы Bollinger."
                )

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

        if bullish == bearish:

            return AnalysisResult(
                direction=None,
                score=0.0,
                reasons=[
                    "Индикаторы конфликтуют."
                ],
                confirmations=0,
                total_checks=checks,
            )

        if bullish > bearish:

            confirmations = bullish

            score = (
                confirmations
                / checks
                * 100
            )

            return AnalysisResult(
                direction=Direction.UP,
                score=score,
                reasons=reasons,
                confirmations=confirmations,
                total_checks=checks,
            )

        confirmations = bearish

        score = (
            confirmations
            / checks
            * 100
        )

        return AnalysisResult(
            direction=Direction.DOWN,
            score=score,
            reasons=reasons,
            confirmations=confirmations,
            total_checks=checks,
        )


signal_engine = SignalEngine()
