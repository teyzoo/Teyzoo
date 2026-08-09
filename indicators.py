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
    macd_histogram: float | None

    bollinger_upper: float | None
    bollinger_middle: float | None
    bollinger_lower: float | None

    atr: float | None

    volatility: float | None


def _ema(
    values: list[float],
    period: int,
) -> float | None:

    if len(values) < period:
        return None

    multiplier = 2 / (
        period + 1
    )

    value = sum(
        values[:period]
    ) / period

    for price in values[period:]:
        value = (
            price - value
        ) * multiplier + value

    return value


def _sma(
    values: list[float],
    period: int,
) -> float | None:

    if len(values) < period:
        return None

    return (
        sum(values[-period:])
        / period
    )


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
            losses.append(
                abs(change)
            )

    if len(gains) < period:
        return None

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


def _atr(
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
        previous = candles[
            index - 1
        ]

        tr = max(
            current.high
            - current.low,
            abs(
                current.high
                - previous.close
            ),
            abs(
                current.low
                - previous.close
            ),
        )

        true_ranges.append(tr)

    if len(true_ranges) < period:
        return None

    return (
        sum(
            true_ranges[-period:]
        )
        / period
    )


def _volatility(
    values: list[float],
    period: int = 20,
) -> float | None:

    if len(values) < period:
        return None

    window = values[-period:]

    mean = (
        sum(window)
        / len(window)
    )

    if mean == 0:
        return None

    variance = (
        sum(
            (
                value - mean
            ) ** 2
            for value in window
        )
        / len(window)
    )

    return (
        sqrt(variance)
        / abs(mean)
        * 100
    )


def calculate_indicators(
    candles: list[Candle],
) -> IndicatorSnapshot:

    if not candles:
        raise ValueError(
            "Нет свечей."
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

    macd_fast = _ema(
        closes,
        12,
    )

    macd_slow = _ema(
        closes,
        26,
    )

    macd = None
    macd_signal = None
    macd_histogram = None

    if (
        macd_fast is not None
        and macd_slow is not None
    ):

        macd_values: list[float] = []

        for index in range(
            25,
            len(closes),
        ):

            fast = _ema(
                closes[: index + 1],
                12,
            )

            slow = _ema(
                closes[: index + 1],
                26,
            )

            if (
                fast is not None
                and slow is not None
            ):
                macd_values.append(
                    fast - slow
                )

        if macd_values:

            macd = macd_values[-1]

            macd_signal = _ema(
                macd_values,
                9,
            )

            if macd_signal is not None:
                macd_histogram = (
                    macd
                    - macd_signal
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

    atr = _atr(
        candles,
        14,
    )

    volatility = _volatility(
        closes,
        20,
    )

    return IndicatorSnapshot(
        price=price,
        ema_fast=ema_fast,
        ema_slow=ema_slow,
        rsi=rsi,
        macd=macd,
        macd_signal=macd_signal,
        macd_histogram=macd_histogram,
        bollinger_upper=(
            bollinger_upper
        ),
        bollinger_middle=(
            bollinger_middle
        ),
        bollinger_lower=(
            bollinger_lower
        ),
        atr=atr,
        volatility=volatility,
    )
