from __future__ import annotations
from market import Candle
from indicators import calculate_indicators
from models import Direction
def detect_trend(
    candles: list[Candle],
) -> Direction | None:
    if len(candles) < 50:
        return None
    indicators = calculate_indicators(
        candles
    )
    if (
        indicators.ema_fast is None
        or indicators.ema_slow is None
    ):
        return None
    if (
        indicators.ema_fast
        > indicators.ema_slow
    ):
        return Direction.UP
    if (
        indicators.ema_fast
        < indicators.ema_slow
    ):
        return Direction.DOWN
    return None
def trend_strength(
    candles: list[Candle],
) -> float:
    if len(candles) < 50:
        return 0.0
    indicators = calculate_indicators(
        candles
    )
    if (
        indicators.ema_fast is None
        or indicators.ema_slow is None
    ):
        return 0.0
    if indicators.price == 0:
        return 0.0
    distance = abs(
        indicators.ema_fast
        - indicators.ema_slow
    )
    strength = (
        distance
        / indicators.price
        * 100
    )
    return min(
        100.0,
        strength * 100,
    )
