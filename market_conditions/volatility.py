from __future__ import annotations

from enum import Enum

from market import Candle


class VolatilityLevel(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"


def calculate_volatility(
    candles: list[Candle],
) -> VolatilityLevel:

    if len(candles) < 20:
        return VolatilityLevel.LOW

    recent = candles[-20:]

    ranges = [
        (
            candle.high
            - candle.low
        )
        for candle in recent
    ]

    closes = [
        candle.close
        for candle in recent
    ]

    average_range = (
        sum(ranges)
        / len(ranges)
    )

    average_price = (
        sum(closes)
        / len(closes)
    )

    if average_price <= 0:
        return VolatilityLevel.LOW

    percentage = (
        average_range
        / average_price
        * 100
    )

    if percentage < 0.01:
        return VolatilityLevel.LOW

    if percentage > 0.30:
        return VolatilityLevel.HIGH

    return VolatilityLevel.NORMAL
