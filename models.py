from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Direction(str, Enum):
    UP = "UP"
    DOWN = "DOWN"


class SignalStatus(str, Enum):
    PENDING = "PENDING"
    WON = "WON"
    LOST = "LOST"
    DRAW = "DRAW"
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

    result_reason: str | None = None
    resolved_at: datetime | None = None

    @property
    def is_pending(self) -> bool:
        return self.status == SignalStatus.PENDING

    @property
    def is_finished(self) -> bool:
        return self.status in {
            SignalStatus.WON,
            SignalStatus.LOST,
            SignalStatus.DRAW,
            SignalStatus.CANCELLED,
        }


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


__all__ = [
    "Direction",
    "SignalStatus",
    "Signal",
    "MarketSnapshot",
    "IndicatorSnapshot",
]
