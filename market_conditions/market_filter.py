from __future__ import annotations

from dataclasses import dataclass

from market_conditions.liquidity import (
    calculate_liquidity,
)

from market_conditions.session import (
    MarketSession,
)

from market_conditions.trend import (
    TrendDirection,
)

from market_conditions.volatility import (
    VolatilityLevel,
)


@dataclass(slots=True)
class MarketFilterResult:
    accepted: bool

    reasons: list[str]
    rejected_reasons: list[str]


def evaluate_market_filter(
    trend: TrendDirection,
    volatility: VolatilityLevel,
    liquidity: float,
    session: MarketSession,
) -> MarketFilterResult:

    reasons: list[str] = []
    rejected: list[str] = []

    if trend == TrendDirection.SIDEWAYS:

        rejected.append(
            "Рынок находится во флэте."
        )

    else:

        reasons.append(
            f"Trend: {trend.value}"
        )

    if volatility == VolatilityLevel.HIGH:

        rejected.append(
            "Слишком высокая волатильность."
        )

    elif volatility == VolatilityLevel.NORMAL:

        reasons.append(
            "Нормальная волатильность."
        )

    else:

        rejected.append(
            "Слишком низкая волатильность."
        )

    if liquidity < 20:

        rejected.append(
            "Недостаточная ликвидность."
        )

    else:

        reasons.append(
            f"Liquidity: {liquidity:.1f}"
        )

    if session == MarketSession.UNKNOWN:

        rejected.append(
            "Неизвестная рыночная сессия."
        )

    else:

        reasons.append(
            f"Session: {session.value}"
        )

    return MarketFilterResult(
        accepted=not rejected,
        reasons=reasons,
        rejected_reasons=rejected,
    )
