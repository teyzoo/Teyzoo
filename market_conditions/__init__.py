from __future__ import annotations

from dataclasses import dataclass

from market import Candle

from market_conditions.liquidity import (
    calculate_liquidity,
)

from market_conditions.market_filter import (
    MarketFilterResult,
    evaluate_market_filter,
)

from market_conditions.session import (
    MarketSession,
    get_market_session,
)

from market_conditions.trend import (
    TrendDirection,
    calculate_trend,
)

from market_conditions.volatility import (
    VolatilityLevel,
    calculate_volatility,
)


@dataclass(slots=True)
class MarketConditionResult:
    accepted: bool

    trend: TrendDirection
    volatility: VolatilityLevel
    session: MarketSession

    liquidity: float

    reasons: list[str]
    rejected_reasons: list[str]


def evaluate_market_conditions(
    candles: list[Candle],
) -> MarketConditionResult:

    trend = calculate_trend(
        candles
    )

    volatility = calculate_volatility(
        candles
    )

    session = get_market_session(
        candles[-1].timestamp
        if candles
        else None
    )

    liquidity = calculate_liquidity(
        candles
    )

    market_filter = (
        evaluate_market_filter(
            trend=trend,
            volatility=volatility,
            liquidity=liquidity,
            session=session,
        )
    )

    return MarketConditionResult(
        accepted=market_filter.accepted,
        trend=trend,
        volatility=volatility,
        session=session,
        liquidity=liquidity,
        reasons=market_filter.reasons,
        rejected_reasons=(
            market_filter.rejected_reasons
        ),
    )
