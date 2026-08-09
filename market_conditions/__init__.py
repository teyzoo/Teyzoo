from __future__ import annotations

from dataclasses import dataclass

from market import Candle
from indicators import calculate_indicators


@dataclass(slots=True)
class MarketConditionResult:
    allowed: bool
    reasons: list[str]
    warnings: list[str]


def evaluate_market_conditions(
    candles: list[Candle],
) -> MarketConditionResult:

    if len(candles) < 50:
        return MarketConditionResult(
            allowed=False,
            reasons=[],
            warnings=[
                "Недостаточно рыночных данных."
            ],
        )

    indicators = calculate_indicators(
        candles
    )

    reasons: list[str] = []
    warnings: list[str] = []

    if (
        indicators.ema_fast is None
        or indicators.ema_slow is None
    ):
        warnings.append(
            "EMA недоступна."
        )
    else:
        reasons.append(
            "EMA рассчитана."
        )

    if indicators.rsi is None:
        warnings.append(
            "RSI недоступен."
        )
    else:
        if (
            indicators.rsi < 20
            or indicators.rsi > 80
        ):
            warnings.append(
                "RSI находится в экстремальной зоне."
            )
        else:
            reasons.append(
                "RSI в рабочем диапазоне."
            )

    if (
        indicators.bollinger_upper is not None
        and indicators.bollinger_lower is not None
    ):
        reasons.append(
            "Bollinger Bands рассчитаны."
        )
    else:
        warnings.append(
            "Bollinger Bands недоступны."
        )

    if len(warnings) >= 2:
        return MarketConditionResult(
            allowed=False,
            reasons=reasons,
            warnings=warnings,
        )

    return MarketConditionResult(
        allowed=True,
        reasons=reasons,
        warnings=warnings,
    )
