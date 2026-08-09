from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
class Direction(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
class SignalStatus(str, Enum):
    PENDING = "PENDING"
    WON = "WON"
    LOST = "LOST"
    CANCELLED = "CANCELLED"
@dataclass(slots=True)
class Signal:
    id: int
    symbol: str
    direction: Direction
    score: float
    close_time: str
    status: SignalStatus = (
        SignalStatus.PENDING
    )
    historical_probability: (
        float | None
    ) = None
