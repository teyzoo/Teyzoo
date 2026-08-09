from __future__ import annotations
from market import Candle
def liquidity_is_acceptable(
    candles: list[Candle],
    period: int = 20,
    minimum_ratio: float = 0.15,
) -> bool:
    if len(candles) < period:
        return False
    volumes = [
        candle.volume
        for candle in candles[-period:]
        if candle.volume > 0
    ]
    # Некоторые FX providers не дают volume.
    # В таком случае не объявляем рынок
    # плохим только из-за отсутствия volume.
    if not volumes:
        return True
    average_volume = (
        sum(volumes)
        / len(volumes)
    )
    if average_volume <= 0:
        return False
    current_volume = (
        candles[-1].volume
    )
    return (
        current_volume
        >= average_volume
        * minimum_ratio
    )
