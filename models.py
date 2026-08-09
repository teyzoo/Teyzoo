from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from datetime import datetime


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

    entry_price: float | None
    exit_price: float | None

    score: float

    historical_probability: float | None

    entry_time: datetime
    expiry_time: datetime

    status: SignalStatus


@dataclass(slots=True)
class MarketSnapshot:
    symbol: str
    price: float
    timestamp: datetime


@dataclass(slots=True)
class IndicatorSnapshot:
    price: float

    ema_fast: float | None
    ema_slow: float | None

    rsi: float | None

    macd: float | None
    macd_signal: float | None

    bollinger_upper: float | None
    bollinger_lower: float | None
