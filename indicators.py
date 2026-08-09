from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

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


def _ema(
    values: list[float],
    period: int,
) -> float | None:

    if len(values) < period:
        return None

    multiplier = 2 / (period + 1)

    result = mean(
        values[:period]
    )

    for value in values[period:]:
        result = (
            value - result
        ) * multiplier + result

    return result


def _ema_series(
    values: list[float],
    period: int,
) -> list[float]:

    if len(values) < period:
        return []

    multiplier = 2 / (period + 1)

    current = mean(
        values[:period]
    )

    result = [current]

    for value in values[period:]:
        current = (
            value - current
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
            losses.append(abs(change))

    avg_gain = mean(
        gains[:period]
    )

    avg_loss = mean(
        losses[:period]
    )

    for index in range(
        period,
        len(gains),
    ):

        avg_gain = (
            (
                avg_gain
                * (period - 1)
            )
            + gains[index]
        ) / period

        avg_loss = (
            (
                avg_loss
                * (period - 1)
            )
            + losses[index]
        ) / period

    if avg_loss == 0:
        return 100.0

    relative_strength = (
        avg_gain / avg_loss
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


def _macd(
    values: list[float],
) -> tuple[
    float | None,
    float | None,
]:

    fast = _ema_series(
        values,
        12,
    )

    slow = _ema_series(
        values,
        26,
    )

    if not fast or not slow:
        return None, None

    offset = 26 - 12

    macd_values: list[float] = []

    for index, slow_value in enumerate(slow):

        fast_index = (
            index + offset
        )

        if fast_index >= len(fast):
            break

        macd_values.append(
            fast[fast_index]
            - slow_value
        )

    if not macd_values:
        return None, None

    macd_value = macd_values[-1]

    signal_series = _ema_series(
        macd_values,
        9,
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

    variance = mean(
        (
            value - middle
        ) ** 2
        for value in window
    )

    standard_deviation = (
        variance ** 0.5
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


def calculate_indicators(
    candles: list[Candle],
) -> IndicatorSnapshot:

    if not candles:
        raise ValueError(
            "Для расчёта индикаторов "
            "нужны свечи."
        )

    closes = [
        candle.close
        for candle in candles
    ]

    price = closes[-1]

    ema_fast = _ema(
        closes,
        9,
    )

    ema_slow = _ema(
        closes,
        21,
    )

    rsi = _rsi(
        closes,
        14,
    )

    macd, macd_signal = _macd(
        closes
    )

    (
        bollinger_upper,
        bollinger_middle,
        bollinger_lower,
    ) = _bollinger(
        closes,
        20,
        2.0,
    )

    return IndicatorSnapshot(
        price=price,
        ema_fast=ema_fast,
        ema_slow=ema_slow,
        rsi=rsi,
        macd=macd,
        macd_signal=macd_signal,
        bollinger_upper=bollinger_upper,
        bollinger_middle=bollinger_middle,
        bollinger_lower=bollinger_lower,
    )
    
