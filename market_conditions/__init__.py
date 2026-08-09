from __future__ import annotations

from dataclasses import dataclass

from indicators import (
    calculate_indicators,
)
from market import Candle


@dataclass(slots=True)
class MarketConditionResult:
    acceptable: bool
    reasons: list[str]
    volatility: float | None


def evaluate_market_conditions(
    candles: list[Candle],
) -> MarketConditionResult:

    if len(candles) < 50:

        return MarketConditionResult(
            acceptable=False,
            reasons=[
                "Недостаточно свечей "
                "для оценки условий рынка."
            ],
            volatility=None,
        )

    indicators = (
        calculate_indicators(
            candles
        )
    )

    reasons: list[str] = []

    # Не принимаем экстремально низкую
    # волатильность.
    if (
        indicators.volatility
        is not None
        and indicators.volatility < 0.005
    ):

        return MarketConditionResult(
            acceptable=False,
            reasons=[
                "Слишком низкая волатильность."
            ],
            volatility=(
                indicators.volatility
            ),
        )

    # Не принимаем экстремально высокую
    # волатильность.
    if (
        indicators.volatility
        is not None
        and indicators.volatility > 5.0
    ):

        return MarketConditionResult(
            acceptable=False,
            reasons=[
                "Слишком высокая волатильность."
            ],
            volatility=(
                indicators.volatility
            ),
        )

    if indicators.volatility is not None:

        reasons.append(
            "Волатильность находится "
            "в допустимом диапазоне."
        )

    if (
        indicators.ema_fast is not None
        and indicators.ema_slow is not None
    ):

        distance = abs(
            indicators.ema_fast
            - indicators.ema_slow
        )

        if distance == 0:

            return MarketConditionResult(
                acceptable=False,
                reasons=[
                    "EMA практически совпадают."
                ],
                volatility=(
                    indicators.volatility
                ),
            )

        reasons.append(
            "На рынке присутствует "
            "выраженное направление."
        )

    return MarketConditionResult(
        acceptable=True,
        reasons=reasons,
        volatility=(
            indicators.volatility
        ),
    )


__all__ = [
    "MarketConditionResult",
    "evaluate_market_conditions",
]
