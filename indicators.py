from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, pstdev

from market import Candle


@dataclass(slots=True)
class IndicatorSnapshot:
    price: float

    ema_fast: float | None
    ema_slow: float | None

    rsi: float | None

    macd: float | None
    macd_signal: float | None

    bollinger_upper: float | None
    bollinger_middle: float | None
    bollinger_lower: float | None


def _ema(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None

    multiplier = 2 / (period + 1)

    value = mean(values[:period])

    for price in values[period:]:
        value = (
            price - value
        ) * multiplier + value

    return value


def _ema_series(
    values: list[float],
    period: int,
) -> list[float]:
    if len(values) < period:
        return []

    multiplier = 2 / (period + 1)

    current = mean(values[:period])

    result = [current]

    for price in values[period:]:
        current = (
            price - current
        ) * multiplier + current

        result.append(current)

    return result


def _rsi(
    values: list[float],
    period: int = 14,
) -> float | None:

    if len(values) <= period:
        return None

    gains: list[float] = []
    losses: list[float] = []

    for index in range(1, period + 1):
        change = (
            values[index]
            - values[index - 1]
        )

        if change >= 0:
            gains.append(change)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(change))

    average_gain = mean(gains)
    average_loss = mean(losses)

    for index in range(
        period + 1,
        len(values),
    ):
        change = (
            values[index]
            - values[index - 1]
        )

        gain = max(change, 0.0)
        loss = max(-change, 0.0)

        average_gain = (
            (average_gain * (period - 1))
            + gain
        ) / period

        average_loss = (
            (average_loss * (period - 1))
            + loss
        ) / period

    if average_loss == 0:
        return 100.0

    rs = (
        average_gain
        / average_loss
    )

    return 100 - (
        100 / (1 + rs)
    )


def _macd(
    values: list[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> tuple[
    float | None,
    float | None,
]:

    if len(values) < slow_period:
        return None, None

    fast_series = _ema_series(
        values,
        fast_period,
    )

    slow_series = _ema_series(
        values,
        slow_period,
    )

    if not fast_series or not slow_series:
        return None, None

    offset = (
        slow_period
        - fast_period
    )

    if offset >= len(fast_series):
        return None, None

    aligned_fast = fast_series[offset:]

    size = min(
        len(aligned_fast),
        len(slow_series),
    )

    macd_series = [
        aligned_fast[index]
        - slow_series[index]
        for index in range(size)
    ]

    if len(macd_series) < signal_period:
        return None, None

    macd_value = macd_series[-1]

    signal_series = _ema_series(
        macd_series,
        signal_period,
    )

    if not signal_series:
        return macd_value, None

    return (
        macd_value,
        signal_series[-1],
    )


def _bollinger(
    values: list[float],
    period: int = 20,
    deviations: float = 2.0,
) -> tuple[
    float | None,
    float | None,
    float | None,
]:

    if len(values) < period:
        return None, None, None

    window = values[-period:]

    middle = mean(window)

    deviation = pstdev(window)

    upper = (
        middle
        + deviations * deviation
    )

    lower = (
        middle
        - deviations * deviation
    )

    return upper, middle, lower


def calculate_indicators(
    candles: list[Candle],
) -> IndicatorSnapshot:

    if not candles:
        raise ValueError(
            "Нет свечей для расчёта индикаторов."
        )

    closes = [
        candle.close
        for candle in candles
    ]

    price = closes[-1]

    return IndicatorSnapshot(
        price=price,

        ema_fast=_ema(
            closes,
            9,
        ),

        ema_slow=_ema(
            closes,
            21,
        ),

        rsi=_rsi(
            closes,
            14,
        ),

        macd=_macd(
            closes
        )[0],

        macd_signal=_macd(
            closes
        )[1],

        bollinger_upper=_bollinger(
            closes
        )[0],

        bollinger_middle=_bollinger(
            closes
        )[1],

        bollinger_lower=_bollinger(
            closes
        )[2],
    )
