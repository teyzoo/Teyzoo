from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from market import Candle


@dataclass(slots=True)
class IndicatorSnapshot:
    """
    Набор индикаторов для одного момента рынка.
    """

    price: float

    ema_fast: float | None
    ema_slow: float | None

    rsi: float | None

    macd: float | None
    macd_signal: float | None
    macd_histogram: float | None

    bollinger_middle: float | None
    bollinger_upper: float | None
    bollinger_lower: float | None

    atr: float | None

    volatility: float | None


def closes(
    candles: list[Candle],
) -> list[float]:
    return [
        candle.close
        for candle in candles
    ]


def ema(
    values: list[float],
    period: int,
) -> float | None:

    if len(values) < period:
        return None

    multiplier = 2 / (period + 1)

    value = sum(
        values[:period]
    ) / period

    for price in values[period:]:
        value = (
            (price - value)
            * multiplier
            + value
        )

    return value


def sma(
    values: list[float],
    period: int,
) -> float | None:

    if len(values) < period:
        return None

    return sum(
        values[-period:]
    ) / period


def rsi(
    values: list[float],
    period: int = 14,
) -> float | None:

    if len(values) <= period:
        return None

    gains: list[float] = []
    losses: list[float] = []

    for index in range(
        1,
        period + 1,
    ):

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

    average_gain = (
        sum(gains) / period
    )

    average_loss = (
        sum(losses) / period
    )

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
            (
                average_gain
                * (period - 1)
            )
            + gain
        ) / period

        average_loss = (
            (
                average_loss
                * (period - 1)
            )
            + loss
        ) / period

    if average_loss == 0:
        return 100.0

    relative_strength = (
        average_gain
        / average_loss
    )

    return (
        100
        - (
            100
            / (
                1
                + relative_strength
            )
        )
    )


def macd(
    values: list[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> tuple[
    float | None,
    float | None,
    float | None,
]:

    if len(values) < slow_period + signal_period:
        return None, None, None

    macd_values: list[float] = []

    for index in range(
        slow_period,
        len(values) + 1,
    ):

        window = values[:index]

        fast = ema(
            window,
            fast_period,
        )

        slow = ema(
            window,
            slow_period,
        )

        if fast is None or slow is None:
            continue

        macd_values.append(
            fast - slow
        )

    if not macd_values:
        return None, None, None

    signal = ema(
        macd_values,
        signal_period,
    )

    current_macd = macd_values[-1]

    if signal is None:
        return (
            current_macd,
            None,
            None,
        )

    histogram = (
        current_macd - signal
    )

    return (
        current_macd,
        signal,
        histogram,
    )


def bollinger(
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

    middle = (
        sum(window)
        / period
    )

    variance = (
        sum(
            (value - middle) ** 2
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
        middle,
        upper,
        lower,
    )


def atr(
    candles: list[Candle],
    period: int = 14,
) -> float | None:

    if len(candles) <= period:
        return None

    true_ranges: list[float] = []

    for index in range(
        1,
        len(candles),
    ):

        current = candles[index]
        previous = candles[index - 1]

        true_range = max(
            current.high - current.low,
            abs(
                current.high
                - previous.close
            ),
            abs(
                current.low
                - previous.close
            ),
        )

        true_ranges.append(
            true_range
        )

    if len(true_ranges) < period:
        return None

    return (
        sum(
            true_ranges[-period:]
        )
        / period
    )


def volatility(
    values: list[float],
    period: int = 20,
) -> float | None:

    if len(values) < period + 1:
        return None

    returns: list[float] = []

    window = values[-(period + 1):]

    for index in range(
        1,
        len(window),
    ):

        previous = window[index - 1]
        current = window[index]

        if previous == 0:
            continue

        returns.append(
            (current - previous)
            / previous
        )

    if not returns:
        return None

    mean = (
        sum(returns)
        / len(returns)
    )

    variance = (
        sum(
            (value - mean) ** 2
            for value in returns
        )
        / len(returns)
    )

    return sqrt(variance)


def calculate_indicators(
    candles: list[Candle],
) -> IndicatorSnapshot:

    if not candles:
        raise ValueError(
            "Нет свечей."
        )

    prices = closes(candles)

    current_price = prices[-1]

    return IndicatorSnapshot(
        price=current_price,

        ema_fast=ema(
            prices,
            9,
        ),

        ema_slow=ema(
            prices,
            21,
        ),

        rsi=rsi(
            prices,
            14,
        ),

        macd=macd(
            prices,
        )[0],

        macd_signal=macd(
            prices,
        )[1],

        macd_histogram=macd(
            prices,
        )[2],

        bollinger_middle=bollinger(
            prices,
        )[0],

        bollinger_upper=bollinger(
            prices,
        )[1],

        bollinger_lower=bollinger(
            prices,
        )[2],

        atr=atr(
            candles,
        ),

        volatility=volatility(
            prices,
        ),
    )
