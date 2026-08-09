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


def _rsi(
    values: list[float],
    period: int = 14,
) -> float | None:

    if len(values) < period + 1:
        return None

    gains: list[float] = []
    losses: list[float] = []

    for index in range(
        len(values) - period,
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

    average_gain = mean(gains)
    average_loss = mean(losses)

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


def _macd(
    values: list[float],
) -> tuple[
    float | None,
    float | None,
]:

    if len(values) < 35:
        return None, None

    ema12 = _ema(
        values,
        12,
    )

    ema26 = _ema(
        values,
        26,
    )

    if (
        ema12 is None
        or ema26 is None
    ):
        return None, None

    macd_value = (
        ema12 - ema26
    )

    macd_history: list[float] = []

    for index in range(
        26,
        len(values) + 1,
    ):

        part = values[:index]

        fast = _ema(
            part,
            12,
        )

        slow = _ema(
            part,
            26,
        )

        if (
            fast is not None
            and slow is not None
        ):
            macd_history.append(
                fast - slow
            )

    if len(macd_history) < 9:
        return macd_value, None

    signal = _ema(
        macd_history,
        9,
    )

    return macd_value, signal


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
