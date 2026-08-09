from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

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


# ============================================================
# EMA
# ============================================================

def calculate_ema(
    values: list[float],
    period: int,
) -> float | None:

    if len(values) < period:

        return None

    multiplier = (
        2.0
        / (period + 1)
    )

    ema = sum(
        values[:period]
    ) / period

    for value in values[period:]:

        ema = (
            (value - ema)
            * multiplier
            + ema
        )

    return ema


# ============================================================
# SMA
# ============================================================

def calculate_sma(
    values: list[float],
    period: int,
) -> float | None:

    if len(values) < period:

        return None

    window = values[
        -period:
    ]

    return (
        sum(window)
        / period
    )


# ============================================================
# RSI
# ============================================================

def calculate_rsi(
    values: list[float],
    period: int = 14,
) -> float | None:

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

            gains.append(
                change
            )

            losses.append(
                0.0
            )

        else:

            gains.append(
                0.0
            )

            losses.append(
                abs(change)
            )

    if len(gains) < period:

        return None

    average_gain = (
        sum(
            gains[:period]
        )
        / period
    )

    average_loss = (
        sum(
            losses[:period]
        )
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
            / (
                1.0
                + relative_strength
            )
        )
    )


# ============================================================
# MACD
# ============================================================

def calculate_macd(
    values: list[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> tuple[
    float | None,
    float | None,
]:

    if len(values) < (
        slow_period
        + signal_period
    ):

        return None, None

    fast_ema = calculate_ema(
        values,
        fast_period,
    )

    slow_ema = calculate_ema(
        values,
        slow_period,
    )

    if (
        fast_ema is None
        or slow_ema is None
    ):

        return None, None

    # --------------------------------------------------------
    # Для корректного MACD signal line
    # рассчитываем исторический ряд MACD.
    # --------------------------------------------------------

    macd_values: list[float] = []

    for index in range(
        slow_period,
        len(values) + 1,
    ):

        subset = values[
            :index
        ]

        fast = calculate_ema(
            subset,
            fast_period,
        )

        slow = calculate_ema(
            subset,
            slow_period,
        )

        if (
            fast is None
            or slow is None
        ):

            continue

        macd_values.append(
            fast - slow
        )

    if len(macd_values) < signal_period:

        return (
            fast_ema - slow_ema,
            None,
        )

    signal = calculate_ema(
        macd_values,
        signal_period,
    )

    return (
        fast_ema - slow_ema,
        signal,
    )


# ============================================================
# BOLLINGER
# ============================================================

def calculate_bollinger(
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

    window = values[
        -period:
    ]

    middle = (
        sum(window)
        / period
    )

    variance = (
        sum(
            (
                value - middle
            ) ** 2
            for value in window
        )
        / period
    )

    standard_deviation = sqrt(
        variance
    )

    upper = (
        middle
        + deviations
        * standard_deviation
    )

    lower = (
        middle
        - deviations
        * standard_deviation
    )

    return (
        upper,
        middle,
        lower,
    )


# ============================================================
# MAIN
# ============================================================

def calculate_indicators(
    candles: list[Candle],
) -> IndicatorSnapshot:

    if not candles:

        raise ValueError(
            "Нет свечей."
        )

    closes = [
        float(candle.close)
        for candle in candles
    ]

    price = closes[-1]

    ema_fast = calculate_ema(
        closes,
        9,
    )

    ema_slow = calculate_ema(
        closes,
        21,
    )

    rsi = calculate_rsi(
        closes,
        14,
    )

    macd, macd_signal = (
        calculate_macd(
            closes,
            fast_period=12,
            slow_period=26,
            signal_period=9,
        )
    )

    (
        bollinger_upper,
        bollinger_middle,
        bollinger_lower,
    ) = calculate_bollinger(
        closes,
        period=20,
        deviations=2.0,
    )

    return IndicatorSnapshot(
        price=price,

        ema_fast=ema_fast,

        ema_slow=ema_slow,

        rsi=rsi,

        macd=macd,

        macd_signal=macd_signal,

        bollinger_upper=(
            bollinger_upper
        ),

        bollinger_middle=(
            bollinger_middle
        ),

        bollinger_lower=(
            bollinger_lower
        ),
    )
