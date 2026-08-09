from __future__ import annotations

from market import Candle


def calculate_liquidity(
    candles: list[Candle],
) -> float:

    if not candles:
        return 0.0

    volumes = [
        candle.volume
        for candle in candles
        if candle.volume > 0
    ]

    if not volumes:
        return 50.0

    recent = volumes[-20:]

    average = (
        sum(recent)
        / len(recent)
    )

    if average <= 0:
        return 0.0

    current = volumes[-1]

    ratio = (
        current
        / average
    )

    score = min(
        100.0,
        ratio * 50.0,
    )

    return max(
        0.0,
        score,
    )
