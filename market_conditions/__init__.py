from __future__ import annotations

from dataclasses import dataclass

from indicators import calculate_indicators
from market import Candle


@dataclass(slots=True)
class MarketConditionResult:
    allowed: bool
    volatility_ok: bool
    trend_ok: bool
    reason: str


def evaluate_market_conditions(
    candles: list[Candle],
) -> MarketConditionResult:

    if len(candles) < 50:
        return MarketConditionResult(
            allowed=False,
            volatility_ok=False,
            trend_ok=False,
            reason=(
                "Недостаточно свечей "
                "для оценки рынка."
            ),
        )

    indicators = calculate_indicators(
        candles
    )

    closes = [
        candle.close
        for candle in candles[-20:]
    ]

    if len(closes) < 20:
        return MarketConditionResult(
            allowed=False,
            volatility_ok=False,
            trend_ok=False,
            reason="Недостаточно данных.",
        )

    highest = max(closes)
    lowest = min(closes)

    current = closes[-1]

    if current <= 0:
        return MarketConditionResult(
            allowed=False,
            volatility_ok=False,
            trend_ok=False,
            reason="Некорректная цена.",
        )

    volatility = (
        highest - lowest
    ) / current * 100

    volatility_ok = (
        0.01
        <= volatility
        <= 2.0
    )

    trend_ok = (
        indicators.ema_fast is not None
        and indicators.ema_slow is not None
    )

    if not volatility_ok:
        return MarketConditionResult(
            allowed=False,
            volatility_ok=False,
            trend_ok=trend_ok,
            reason=(
                "Волатильность рынка "
                "вне допустимого диапазона."
            ),
        )

    if not trend_ok:
        return MarketConditionResult(
            allowed=False,
            volatility_ok=True,
            trend_ok=False,
            reason=(
                "Не удалось определить тренд."
            ),
        )

    return MarketConditionResult(
        allowed=True,
        volatility_ok=True,
        trend_ok=True,
        reason="Рыночные условия подходят.",
    )


__all__ = [
    "MarketConditionResult",
    "evaluate_market_conditions",
]
