from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Sequence

from market import Candle


@dataclass(slots=True)
class IndicatorResult:
    price: float

    ema_fast: float | None
    ema_slow: float | None

    rsi: float | None

    macd: float | None
    macd_signal: float | None

    bollinger_upper: float | None
    bollinger_lower: float | None


def _prices(
    candles: Sequence[Candle],
) -> list[float]:
    values = [
        float(candle.close)
        for candle in candles
    ]

    if not values:
        return []

    if any(
        not isfinite(value)
        for value in values
    ):
        raise ValueError(
            "Candle prices contain non-finite values."
        )

    return values


def _sma(
    values: Sequence[float],
    period: int,
) -> float | None:
    if period <= 0:
        raise ValueError(
            "SMA period must be greater than 0."
        )

    if len(values) < period:
        return None

    return sum(
        values[-period:]
    ) / period


def _ema_series(
    values: Sequence[float],
    period: int,
) -> list[float]:
    if period <= 0:
        raise ValueError(
            "EMA period must be greater than 0."
        )

    if len(values) < period:
        return []

    multiplier = 2.0 / (
        period + 1.0
    )

    previous = sum(
        values[:period]
    ) / period

    result = [previous]

    for value in values[period:]:
        previous = (
            previous
            + multiplier
            * (value - previous)
        )

        result.append(previous)

    return result


def _ema(
    values: Sequence[float],
    period: int,
) -> float | None:
    series = _ema_series(
        values,
        period,
    )

    return series[-1] if series else None


def _rsi(
    values: Sequence[float],
    period: int = 14,
) -> float | None:
    if period <= 0:
        raise ValueError(
            "RSI period must be greater than 0."
        )

    if len(values) < period + 1:
        return None

    gains: list[float] = []
    losses: list[float] = []

    for current, previous in zip(
        values[1:],
        values[:-1],
    ):
        change = current - previous

        gains.append(
            max(change, 0.0)
        )

        losses.append(
            max(-change, 0.0)
        )

    average_gain = (
        sum(gains[:period])
        / period
    )

    average_loss = (
        sum(losses[:period])
        / period
    )

    for index in range(
        period,
        len(gains),
    ):
        average_gain = (
            (
                average_gain
                * (period - 1)
            )
            + gains[index]
        ) / period

        average_loss = (
            (
                average_loss
                * (period - 1)
            )
            + losses[index]
        ) / period

    if average_loss == 0.0:
        return (
            50.0
            if average_gain == 0.0
            else 100.0
        )

    rs = (
        average_gain
        / average_loss
    )

    return 100.0 - (
        100.0 / (1.0 + rs)
    )


def _macd(
    values: Sequence[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> tuple[
    float | None,
    float | None,
]:
    if (
        fast_period <= 0
        or slow_period <= 0
        or signal_period <= 0
    ):
        raise ValueError(
            "MACD periods must be greater than 0."
        )

    if fast_period >= slow_period:
        raise ValueError(
            "MACD fast period must be smaller than slow period."
        )

    if len(values) < slow_period:
        return None, None

    fast = _ema_series(
        values,
        fast_period,
    )

    slow = _ema_series(
        values,
        slow_period,
    )

    if not fast or not slow:
        return None, None

    macd_values: list[float] = []

    for candle_index in range(
        slow_period - 1,
        len(values),
    ):
        fast_index = (
            candle_index
            - (fast_period - 1)
        )

        slow_index = (
            candle_index
            - (slow_period - 1)
        )

        if not (
            0 <= fast_index < len(fast)
            and 0 <= slow_index < len(slow)
        ):
            continue

        macd_values.append(
            fast[fast_index]
            - slow[slow_index]
        )

    if not macd_values:
        return None, None

    macd_value = macd_values[-1]

    signal = _ema_series(
        macd_values,
        signal_period,
    )

    return (
        macd_value,
        signal[-1] if signal else None,
    )


def _bollinger_bands(
    values: Sequence[float],
    period: int = 20,
    deviations: float = 2.0,
) -> tuple[
    float | None,
    float | None,
]:
    if period <= 0:
        raise ValueError(
            "Bollinger period must be greater than 0."
        )

    if deviations < 0:
        raise ValueError(
            "Bollinger deviations cannot be negative."
        )

    if len(values) < period:
        return None, None

    window = list(
        values[-period:]
    )

    mean = sum(window) / period

    variance = sum(
        (value - mean) ** 2
        for value in window
    ) / period

    std = variance ** 0.5

    return (
        mean + deviations * std,
        mean - deviations * std,
    )


def calculate_indicators(
    candles: Sequence[Candle],
) -> IndicatorResult:
    if not candles:
        raise ValueError(
            "Cannot calculate indicators without candles."
        )

    values = _prices(candles)

    return IndicatorResult(
        price=values[-1],

        ema_fast=_ema(
            values,
            9,
        ),

        ema_slow=_ema(
            values,
            21,
        ),

        rsi=_rsi(
            values,
            14,
        ),

        macd=_macd(
            values,
            12,
            26,
            9,
        )[0],

        macd_signal=_macd(
            values,
            12,
            26,
            9,
        )[1],

        bollinger_upper=_bollinger_bands(
            values,
            20,
            2.0,
        )[0],

        bollinger_lower=_bollinger_bands(
            values,
            20,
            2.0,
        )[1],
    )


__all__ = [
    "IndicatorResult",
    "calculate_indicators",
]
