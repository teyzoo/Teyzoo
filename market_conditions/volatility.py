from __future__ import annotations
from market import Candle
from indicators import calculate_indicators
def volatility_is_acceptable(
    candles: list[Candle],
    minimum_atr_ratio: float = 0.00005,
    maximum_atr_ratio: float = 0.03,
) -> bool:
    if len(candles) < 30:
        return False
    indicators = calculate_indicators(
        candles
    )
    if indicators.atr is None:
        return False
    price = indicators.price
    if price <= 0:
        return False
    atr_ratio = (
        indicators.atr
        / price
    )
    return (
        minimum_atr_ratio
        <= atr_ratio
        <= maximum_atr_ratio
    )
def average_candle_range(
    candles: list[Candle],
    period: int = 20,
) -> float:
    if not candles:
        return 0.0
    window = candles[-period:]
    return (
        sum(
            candle.high - candle.low
            for candle in window
        )
        / len(window)
    )
