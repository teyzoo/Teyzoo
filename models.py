from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Direction(str, Enum):
    UP = "UP"
    DOWN = "DOWN"


class SignalResult(str, Enum):
    PENDING = "PENDING"
    WIN = "WIN"
    LOSS = "LOSS"
    DRAW = "DRAW"


@dataclass(slots=True)
class SignalRecord:
    id: int
    symbol: str
    direction: Direction
    score: float
    historical_probability: float | None
    signal_time: str
    close_time: str
    result: SignalResult
    entry_price: float | None
    exit_price: float | None
