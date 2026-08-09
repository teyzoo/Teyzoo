from __future__ import annotations
from market import Candle
from .liquidity import (
    liquidity_is_acceptable,
)
from .session import (
    is_market_session_active,
)
from .trend import (
    detect_trend,
)
from .volatility import (
    volatility_is_acceptable,
)
def market_is_tradeable(
    candles: list[Candle],
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not is_market_session_active():
        reasons.append(
            "Неактивная торговая сессия."
        )
    if not volatility_is_acceptable(
        candles
    ):
        reasons.append(
            "Неподходящая волатильность."
        )
    if not liquidity_is_acceptable(
        candles
    ):
        reasons.append(
            "Недостаточная ликвидность."
        )
    if detect_trend(candles) is None:
        reasons.append(
            "Не определён устойчивый тренд."
        )
    return (
        len(reasons) == 0,
        reasons,
    )
