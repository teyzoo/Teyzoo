from __future__ import annotations

from market import Candle
from models import IndicatorSnapshot


def _ema(
    values: list[float],
    period: int,
) -> float | None:

    if len(values) < period:
        return None

    multiplier = (
        2 / (period + 1)
    )

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

    avg_gain = (
        sum(gains[:period])
        / period
    )

    avg_loss = (
        sum(losses[:period])
        / period
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
        avg_gain
        / avg_loss
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


def _bollinger(
    values: list[float],
    period: int = 20,
    deviations: float = 2.0,
) -> tuple[
    float | None,
    float | None,
]:

    if len(values) < period:
        return None, None

    window = values[-period:]

    mean = (
        sum(window)
        / period
    )

    variance = (
        sum(
            (value - mean) ** 2
            for value in window
        )
        / period
    )

    stddev = variance ** 0.5

    return (
        mean + deviations * stddev,
        mean - deviations * stddev,
    )


def calculate_indicators(
    candles: list[Candle],
) -> IndicatorSnapshot:

    if not candles:
        raise ValueError(
            "Candles cannot be empty."
        )

    prices = [
        candle.close
        for candle in candles
    ]

    price = prices[-1]

    ema_fast = _ema(
        prices,
        12,
    )

    ema_slow = _ema(
        prices,
        26,
    )

    rsi = _rsi(
        prices,
        14,
    )

    macd = None
    macd_signal = None

    if len(prices) >= 35:

        macd_values: list[float] = []

        for index in range(
            26,
            len(prices) + 1,
        ):

            window = prices[:index]

            fast = _ema(
                window,
                12,
            )

            slow = _ema(
                window,
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

    upper, lower = _bollinger(
        prices,
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
        bollinger_upper=upper,
        bollinger_lower=lower,
    )
