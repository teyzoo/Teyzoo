from __future__ import annotations

from dataclasses import dataclass
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


# =========================================================
# BASIC HELPERS
# =========================================================

def _prices(
    candles: Sequence[Candle],
) -> list[float]:
    return [
        float(candle.close)
        for candle in candles
    ]


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

    window = values[-period:]

    return sum(window) / period


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

    initial = (
        sum(values[:period])
        / period
    )

    multiplier = (
        2.0
        / (period + 1)
    )

    result = [initial]

    previous = initial

    for value in values[period:]:
        current = (
            (value - previous)
            * multiplier
            + previous
        )

        result.append(current)

        previous = current

    return result


def _ema(
    values: Sequence[float],
    period: int,
) -> float | None:
    series = _ema_series(
        values,
        period,
    )

    if not series:
        return None

    return series[-1]


# =========================================================
# RSI
# =========================================================

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

    for index in range(
        1,
        len(values),
    ):
        change = (
            values[index]
            - values[index - 1]
        )

        if change > 0:
            gains.append(change)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(
                abs(change)
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

    if average_loss == 0:
        if average_gain == 0:
            return 50.0

        return 100.0

    relative_strength = (
        average_gain
        / average_loss
    )

    return (
        100.0
        - (
            100.0
            / (1.0 + relative_strength)
        )
    )


# =========================================================
# MACD
# =========================================================

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
            "MACD fast period must be "
            "smaller than slow period."
        )

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

    # EMA series have different starting
    # positions. Align them by timestamp/
    # candle index.
    fast_offset = (
        fast_period - 1
    )

    slow_offset = (
        slow_period - 1
    )

    macd_values: list[float] = []

    for index in range(
        slow_offset,
        len(values),
    ):
        fast_index = (
            index - fast_offset
        )

        slow_index = (
            index - slow_offset
        )

        if (
            fast_index < 0
            or fast_index >= len(fast_series)
            or slow_index < 0
            or slow_index >= len(slow_series)
        ):
            continue

        macd_values.append(
            fast_series[fast_index]
            - slow_series[slow_index]
        )

    if not macd_values:
        return None, None

    macd_value = macd_values[-1]

    signal_series = _ema_series(
        macd_values,
        signal_period,
    )

    if not signal_series:
        return macd_value, None

    return (
        macd_value,
        signal_series[-1],
    )


# =========================================================
# BOLLINGER BANDS
# =========================================================

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

    mean = (
        sum(window)
        / period
    )

    variance = (
        sum(
            (
                value - mean
            ) ** 2
            for value in window
        )
        / period
    )

    standard_deviation = (
        variance ** 0.5
    )

    upper = (
        mean
        + deviations
        * standard_deviation
    )

    lower = (
        mean
        - deviations
        * standard_deviation
    )

    return upper, lower


# =========================================================
# PUBLIC CALCULATOR
# =========================================================

def calculate_indicators(
    candles: Sequence[Candle],
) -> IndicatorResult:
    """
    Рассчитывает основные индикаторы,
    используемые signal_engine.py.

    EMA:
        9 / 21

    RSI:
        14

    MACD:
        12 / 26 / 9

    Bollinger:
        20 / 2
    """

    if not candles:
        raise ValueError(
            "Cannot calculate indicators "
            "without candles."
        )

    values = _prices(candles)

    price = values[-1]

    ema_fast = _ema(
        values,
        9,
    )

    ema_slow = _ema(
        values,
        21,
    )

    rsi = _rsi(
        values,
        14,
    )

    macd, macd_signal = _macd(
        values,
        fast_period=12,
        slow_period=26,
        signal_period=9,
    )

    (
        bollinger_upper,
        bollinger_lower,
    ) = _bollinger_bands(
        values,
        period=20,
        deviations=2.0,
    )

    return IndicatorResult(
        price=price,
        ema_fast=ema_fast,
        ema_slow=ema_slow,
        rsi=rsi,
        macd=macd,
        macd_signal=macd_signal,
        bollinger_upper=bollinger_upper,
        bollinger_lower=bollinger_lower,
    )


__all__ = [
    "IndicatorResult",
    "calculate_indicators",
]
