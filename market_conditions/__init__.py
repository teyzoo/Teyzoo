from __future__ import annotations
from dataclasses import dataclass
from market import Candle
from indicators import calculate_indicators
@dataclass(slots=True)
class MarketConditionResult:
    acceptable: bool
    volatility_ok: bool
    trend_ok: bool
    liquidity_ok: bool
    reason: str
def evaluate_market_conditions(
    candles: list[Candle],
) -> MarketConditionResult:
    if len(candles) < 50:
        return MarketConditionResult(
            acceptable=False,
            volatility_ok=False,
            trend_ok=False,
            liquidity_ok=False,
            reason="Недостаточно свечей.",
        )
    indicators = calculate_indicators(
        candles
    )
    volatility_ok = True
    trend_ok = True
    liquidity_ok = True
    recent = candles[-20:]
    average_range = (
        sum(
            candle.high - candle.low
            for candle in recent
        )
        / len(recent)
    )
    if average_range <= 0:
        volatility_ok = False
    if indicators.atr is not None:
        if indicators.atr <= 0:
            volatility_ok = False
    if (
        indicators.ema_fast is None
        or indicators.ema_slow is None
    ):
        trend_ok = False
    volumes = [
        candle.volume
        for candle in recent
        if candle.volume > 0
    ]
    if not volumes:
        liquidity_ok = True
    else:
        average_volume = (
            sum(volumes)
            / len(volumes)
        )
        last_volume = (
            recent[-1].volume
        )
        # Если последний объём совсем
        # аномально низкий относительно
        # недавней истории — пропускаем.
        if (
            average_volume > 0
            and last_volume
            < average_volume * 0.15
        ):
            liquidity_ok = False
    acceptable = (
        volatility_ok
        and trend_ok
        and liquidity_ok
    )
    if acceptable:
        reason = (
            "Рыночные условия приемлемы."
        )
    else:
        failed = []
        if not volatility_ok:
            failed.append(
                "волатильность"
            )
        if not trend_ok:
            failed.append(
                "тренд"
            )
        if not liquidity_ok:
            failed.append(
                "ликвидность"
            )
        reason = (
            "Не пройдены условия: "
            + ", ".join(failed)
        )
    return MarketConditionResult(
        acceptable=acceptable,
        volatility_ok=volatility_ok,
        trend_ok=trend_ok,
        liquidity_ok=liquidity_ok,
        reason=reason,
    )
__all__ = [
    "MarketConditionResult",
    "evaluate_market_conditions",
]
