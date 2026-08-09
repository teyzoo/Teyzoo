from __future__ import annotations

from market import Candle


def calculate_trend_strength(
    candles: list[Candle],
    period: int = 30,
) -> float:

    if len(candles) < 2:
        return 0.0

    candles = candles[-period:]

    first = candles[0].close
    last = candles[-1].close

    if first == 0:
        return 0.0

    return (
        abs(last - first)
        / first
        * 100
    )


def trend_direction(
    candles: list[Candle],
) -> str | None:

    if len(candles) < 2:
        return None

    first = candles[0].close
    last = candles[-1].close

    if last > first:
        return "UP"

    if last < first:
        return "DOWN"

    return None
