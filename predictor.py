from __future__ import annotations

from dataclasses import dataclass

from indicators import (
    calculate_indicators,
)
from market import Candle
from models import Direction


@dataclass(slots=True)
class Prediction:
    direction: Direction | None
    confidence: float
    reasons: list[str]


class Predictor:

    def predict(
        self,
        candles: list[Candle],
    ) -> Prediction:

        if len(candles) < 50:

            return Prediction(
                direction=None,
                confidence=0.0,
                reasons=[
                    "Недостаточно истории."
                ],
            )

        indicators = (
            calculate_indicators(
                candles
            )
        )

        up_weight = 0.0
        down_weight = 0.0

        reasons: list[str] = []

        # Тренд имеет наибольший вес.
        if (
            indicators.ema_fast
            is not None
            and indicators.ema_slow
            is not None
        ):

            if (
                indicators.ema_fast
                > indicators.ema_slow
            ):

                up_weight += 2.0

                reasons.append(
                    "EMA подтверждает восходящий тренд."
                )

            elif (
                indicators.ema_fast
                < indicators.ema_slow
            ):

                down_weight += 2.0

                reasons.append(
                    "EMA подтверждает нисходящий тренд."
                )

        # MACD.
        if (
            indicators.macd
            is not None
            and indicators.macd_signal
            is not None
        ):

            if (
                indicators.macd
                > indicators.macd_signal
            ):

                up_weight += 2.0

                reasons.append(
                    "MACD выше сигнальной линии."
                )

            elif (
                indicators.macd
                < indicators.macd_signal
            ):

                down_weight += 2.0

                reasons.append(
                    "MACD ниже сигнальной линии."
                )

        # RSI.
        if indicators.rsi is not None:

            if indicators.rsi < 30:

                up_weight += 1.5

                reasons.append(
                    "RSI показывает сильную перепроданность."
                )

            elif indicators.rsi > 70:

                down_weight += 1.5

                reasons.append(
                    "RSI показывает сильную перекупленность."
                )

            elif indicators.rsi > 50:

                up_weight += 0.5

            elif indicators.rsi < 50:

                down_weight += 0.5

        # Bollinger.
        if (
            indicators.bollinger_upper
            is not None
            and indicators.bollinger_lower
            is not None
        ):

            if (
                indicators.price
                <= indicators.bollinger_lower
            ):

                up_weight += 1.0

                reasons.append(
                    "Цена находится возле нижней полосы Bollinger."
                )

            elif (
                indicators.price
                >= indicators.bollinger_upper
            ):

                down_weight += 1.0

                reasons.append(
                    "Цена находится возле верхней полосы Bollinger."
                )

        total = (
            up_weight
            + down_weight
        )

        if total <= 0:

            return Prediction(
                direction=None,
                confidence=0.0,
                reasons=[
                    "Нет достаточных подтверждений."
                ],
            )

        if up_weight == down_weight:

            return Prediction(
                direction=None,
                confidence=0.0,
                reasons=[
                    "Направления конфликтуют."
                ],
            )

        if up_weight > down_weight:

            confidence = (
                up_weight
                / total
                * 100
            )

            direction = Direction.UP

        else:

            confidence = (
                down_weight
                / total
                * 100
            )

            direction = Direction.DOWN

        return Prediction(
            direction=direction,
            confidence=confidence,
            reasons=reasons,
        )


predictor = Predictor()
