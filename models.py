from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
class Direction(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
class SignalStatus(str, Enum):
    CREATED = "CREATED"
    WARNING_SENT = "WARNING_SENT"
    CLOSED = "CLOSED"
    WIN = "WIN"
    LOSS = "LOSS"
    DRAW = "DRAW"
    ERROR = "ERROR"
@dataclass(slots=True)
class Signal:
    id: int
    symbol: str
    direction: Direction
    score: float
    historical_probability: float | None
    entry_price: float | None
    exit_price: float | None
    created_at: str
    close_time: str
    status: SignalStatus
    warning_sent: bool
    result_checked: bool
@dataclass(slots=True)
class User:
    telegram_id: int
    username: str | None
    first_name: str | None
    is_active: bool
    is_admin: bool
@dataclass(slots=True)
class SignalStatistics:
    total: int
    wins: int
    losses: int
    draws: int
    win_rate: float
    average_score: float
