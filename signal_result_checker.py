from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from models import Direction


logger = logging.getLogger(
    "signal_results"
)


@dataclass(slots=True)
class SignalCheckResult:
    signal_id: int
    direction: Direction

    entry_price: float
    exit_price: float

    won: bool

    checked_at: datetime

    reason: str


def check_signal_result(
    signal_id: int,
    direction: Direction,
    entry_price: float,
    exit_price: float,
    checked_at: datetime,
) -> SignalCheckResult:

    if entry_price <= 0:
        raise ValueError(
            "Entry price должен быть больше 0."
        )

    if exit_price <= 0:
        raise ValueError(
            "Exit price должен быть больше 0."
        )

    if direction == Direction.UP:

        won = (
            exit_price
            > entry_price
        )

        reason = (
            "Цена закрытия выше "
            "цены входа."
            if won
            else
            "Цена закрытия не выше "
            "цены входа."
        )

    elif direction == Direction.DOWN:

        won = (
            exit_price
            < entry_price
        )

        reason = (
            "Цена закрытия ниже "
            "цены входа."
            if won
            else
            "Цена закрытия не ниже "
            "цены входа."
        )

    else:

        raise ValueError(
            f"Неизвестное направление: {direction}"
        )

    return SignalCheckResult(
        signal_id=signal_id,
        direction=direction,
        entry_price=entry_price,
        exit_price=exit_price,
        won=won,
        checked_at=checked_at,
        reason=reason,
    )
