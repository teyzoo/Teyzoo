from __future__ import annotations

from dataclasses import dataclass

from market import Candle


@dataclass(slots=True)
class MarketConditionResult:
    acceptable: bool
    volatility: float
    trend_strength: float
    reasons: list[str]


def evaluate_market_conditions(
    candles: list[Candle],
) -> MarketConditionResult:

    if len(candles) < 30:

        return MarketConditionResult(
            acceptable=False,
            volatility=0.0,
            trend_strength=0.0,
            reasons=[
                "Недостаточно свечей."
            ],
        )

    recent = candles[-30:]

    closes = [
        candle.close
        for candle in recent
    ]

    if not closes:

        return MarketConditionResult(
            acceptable=False,
            volatility=0.0,
            trend_strength=0.0,
            reasons=[
                "Нет цен закрытия."
            ],
        )

    average_price = (
        sum(closes)
        / len(closes)
    )

    if average_price <= 0:

        return MarketConditionResult(
            acceptable=False,
            volatility=0.0,
            trend_strength=0.0,
            reasons=[
                "Некорректная цена."
            ],
        )

    changes: list[float] = []

    for index in range(
        1,
        len(closes),
    ):

        previous = closes[index - 1]
        current = closes[index]

        if previous == 0:
            continue

        changes.append(
            abs(
                current - previous
            )
            / previous
            * 100
        )

    if not changes:

        return MarketConditionResult(
            acceptable=False,
            volatility=0.0,
            trend_strength=0.0,
            reasons=[
                "Недостаточно изменений цены."
            ],
        )

    volatility = (
        sum(changes)
        / len(changes)
    )

    first = closes[0]
    last = closes[-1]

    trend_strength = (
        abs(last - first)
        / first
        * 100
        if first
        else 0.0
    )

    reasons: list[str] = []

    if volatility < 0.0001:

        reasons.append(
            "Рынок практически не движется."
        )

    elif volatility > 1.5:

        reasons.append(
            "Слишком высокая волатильность."
        )

    else:

        reasons.append(
            "Волатильность находится "
            "в допустимом диапазоне."
        )

    if trend_strength < 0.02:

        reasons.append(
            "Выраженный тренд отсутствует."
        )

    else:

        reasons.append(
            "Наблюдается движение цены."
        )

    acceptable = (
        0.0001 <= volatility <= 1.5
        and trend_strength >= 0.02
    )

    return MarketConditionResult(
        acceptable=acceptable,
        volatility=volatility,
        trend_strength=trend_strength,
        reasons=reasons,
    )
