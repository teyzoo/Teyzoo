from __future__ import annotations

from enum import Enum

from market import Candle


class TrendDirection(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    SIDEWAYS = "SIDEWAYS"


def calculate_trend(
    candles: list[Candle],
) -> TrendDirection:

    if len(candles) < 20:
        return TrendDirection.SIDEWAYS

    closes = [
        candle.close
        for candle in candles
    ]

    short = (
        sum(closes[-5:])
        / 5
    )

    long = (
        sum(closes[-20:])
        / 20
    )

    if long == 0:
        return TrendDirection.SIDEWAYS

    difference = (
        (short - long)
        / long
        * 100
    )

    if difference >= 0.03:
        return TrendDirection.BULLISH

    if difference <= -0.03:
        return TrendDirection.BEARISH

    return TrendDirection.SIDEWAYS
