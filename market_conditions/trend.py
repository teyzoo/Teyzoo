from __future__ import annotations

from enum import Enum

from market import Candle


class TrendDirection(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    SIDEWAYS = "SIDEWAYS"


def calculate_trend(
    candles: list[Candle],
    short_period: int = 5,
    long_period: int = 20,
    threshold_percent: float = 0.03,
) -> TrendDirection:
    """
    Определяет направление тренда.

    Используется отношение короткой средней
    к длинной средней.

    threshold_percent:
        минимальное отличие в процентах,
        при котором считаем рынок направленным.
    """

    short_period = max(
        2,
        int(short_period),
    )

    long_period = max(
        short_period + 1,
        int(long_period),
    )

    threshold_percent = max(
        0.0,
        float(threshold_percent),
    )

    if len(candles) < long_period:
        return TrendDirection.SIDEWAYS

    closes = [
        float(candle.close)
        for candle in candles
        if float(candle.close) > 0
    ]

    if len(closes) < long_period:
        return TrendDirection.SIDEWAYS

    short_average = (
        sum(
            closes[-short_period:]
        )
        / short_period
    )

    long_average = (
        sum(
            closes[-long_period:]
        )
        / long_period
    )

    if long_average <= 0:
        return TrendDirection.SIDEWAYS

    difference = (
        (
            short_average
            - long_average
        )
        / long_average
        * 100.0
    )

    if (
        difference
        >= threshold_percent
    ):
        return TrendDirection.BULLISH

    if (
        difference
        <= -threshold_percent
    ):
        return TrendDirection.BEARISH

    return TrendDirection.SIDEWAYS


def trend_strength(
    candles: list[Candle],
    short_period: int = 5,
    long_period: int = 20,
) -> float:
    """
    Возвращает абсолютную силу тренда в процентах.
    """

    short_period = max(
        2,
        int(short_period),
    )

    long_period = max(
        short_period + 1,
        int(long_period),
    )

    if len(candles) < long_period:
        return 0.0

    closes = [
        float(candle.close)
        for candle in candles
        if float(candle.close) > 0
    ]

    if len(closes) < long_period:
        return 0.0

    short_average = (
        sum(
            closes[-short_period:]
        )
        / short_period
    )

    long_average = (
        sum(
            closes[-long_period:]
        )
        / long_period
    )

    if long_average <= 0:
        return 0.0

    return abs(
        (
            short_average
            - long_average
        )
        / long_average
        * 100.0
    )


__all__ = [
    "TrendDirection",
    "calculate_trend",
    "trend_strength",
]
