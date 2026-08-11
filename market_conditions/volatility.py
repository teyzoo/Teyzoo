from __future__ import annotations

from enum import Enum

from market import Candle


class VolatilityLevel(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"


def calculate_volatility(
    candles: list[Candle],
    period: int = 20,
    low_threshold: float = 0.01,
    high_threshold: float = 0.30,
) -> VolatilityLevel:
    """
    Определяет относительную волатильность рынка.

    Используется:

        average(high - low)
        ------------------- * 100
        average(close)

    """

    period = max(
        2,
        int(period),
    )

    low_threshold = max(
        0.0,
        float(low_threshold),
    )

    high_threshold = max(
        low_threshold,
        float(high_threshold),
    )

    if len(candles) < period:
        return VolatilityLevel.LOW

    recent = candles[-period:]

    ranges: list[float] = []
    closes: list[float] = []

    for candle in recent:
        high = float(
            candle.high
        )
        low = float(
            candle.low
        )
        close = float(
            candle.close
        )

        if (
            high <= 0
            or low <= 0
            or close <= 0
            or high < low
        ):
            continue

        ranges.append(
            high - low
        )
        closes.append(
            close
        )

    if not ranges or not closes:
        return VolatilityLevel.LOW

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
        * 100.0
    )

    if percentage < low_threshold:
        return VolatilityLevel.LOW

    if percentage > high_threshold:
        return VolatilityLevel.HIGH

    return VolatilityLevel.NORMAL


def volatility_percent(
    candles: list[Candle],
    period: int = 20,
) -> float:
    """
    Возвращает фактическую относительную
    волатильность в процентах.
    """

    period = max(
        2,
        int(period),
    )

    if len(candles) < period:
        return 0.0

    recent = candles[-period:]

    ranges: list[float] = []
    closes: list[float] = []

    for candle in recent:
        high = float(
            candle.high
        )
        low = float(
            candle.low
        )
        close = float(
            candle.close
        )

        if (
            high <= 0
            or low <= 0
            or close <= 0
            or high < low
        ):
            continue

        ranges.append(
            high - low
        )
        closes.append(
            close
        )

    if not ranges or not closes:
        return 0.0

    average_range = (
        sum(ranges)
        / len(ranges)
    )

    average_price = (
        sum(closes)
        / len(closes)
    )

    if average_price <= 0:
        return 0.0

    return (
        average_range
        / average_price
        * 100.0
    )


__all__ = [
    "VolatilityLevel",
    "calculate_volatility",
    "volatility_percent",
]
