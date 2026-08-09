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
    atr: float | None
def _ema(
    values: list[float],
    period: int,
) -> float | None:
    if len(values) < period:
        return None
    multiplier = 2 / (period + 1)
    result = sum(
        values[:period]
    ) / period
    for value in values[period:]:
        result = (
            (value - result)
            * multiplier
            + result
        )
    return result
def _ema_series(
    values: list[float],
    period: int,
) -> list[float]:
    if len(values) < period:
        return []
    multiplier = 2 / (period + 1)
    first = (
        sum(values[:period])
        / period
    )
    result = [first]
    previous = first
    for value in values[period:]:
        current = (
            (value - previous)
            * multiplier
            + previous
        )
        result.append(current)
        previous = current
    return result
def _rsi(
    closes: list[float],
    period: int = 14,
) -> float | None:
    if len(closes) <= period:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for index in range(
        1,
        period + 1,
    ):
        difference = (
            closes[index]
            - closes[index - 1]
        )
        if difference >= 0:
            gains.append(difference)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(-difference)
    average_gain = (
        sum(gains) / period
    )
    average_loss = (
        sum(losses) / period
    )
    for index in range(
        period + 1,
        len(closes),
    ):
        difference = (
            closes[index]
            - closes[index - 1]
        )
        gain = max(
            difference,
            0.0,
        )
        loss = max(
            -difference,
            0.0,
        )
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
            / (1 + relative_strength)
        )
    )
def _bollinger(
    closes: list[float],
    period: int = 20,
    deviations: float = 2.0,
) -> tuple[
    float | None,
    float | None,
    float | None,
]:
    if len(closes) < period:
        return None, None, None
    window = closes[-period:]
    middle = (
        sum(window) / period
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
def calculate_indicators(
    candles: list[Candle],
) -> IndicatorSnapshot:
    if not candles:
        raise ValueError(
            "candles cannot be empty"
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
    fast_series = _ema_series(
        closes,
        12,
    )
    slow_series = _ema_series(
        closes,
        26,
    )
    macd = None
    macd_signal = None
    if fast_series and slow_series:
        # Приводим серии к общей длине.
        offset = (
            len(fast_series)
            - len(slow_series)
        )
        if offset >= 0:
            aligned_fast = (
                fast_series[offset:]
            )
            macd_series = [
                fast - slow
                for fast, slow
                in zip(
                    aligned_fast,
                    slow_series,
                )
            ]
        else:
            offset = abs(offset)
            aligned_slow = (
                slow_series[offset:]
            )
            macd_series = [
                fast - slow
                for fast, slow
                in zip(
                    fast_series,
                    aligned_slow,
                )
            ]
        if macd_series:
            macd = macd_series[-1]
            signal_series = _ema_series(
                macd_series,
                9,
            )
            if signal_series:
                macd_signal = (
                    signal_series[-1]
                )
    (
        bollinger_upper,
        bollinger_middle,
        bollinger_lower,
    ) = _bollinger(
        closes,
        period=20,
        deviations=2,
    )
    atr = _atr(
        candles,
        period=14,
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
        atr=atr,
    )
