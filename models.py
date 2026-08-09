from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Direction(str, Enum):
    UP = "UP"
    DOWN = "DOWN"


class SignalStatus(str, Enum):
    PENDING = "pending"
    WIN = "win"
    LOSS = "loss"
    CANCELLED = "cancelled"


@dataclass
class MarketCandle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass
class Signal:
    symbol: str
    direction: Direction
    score: float
    close_time: datetime
    reasons: list[str]

    @property
    def direction_text(self) -> str:
        if self.direction == Direction.UP:
            return "📈 ВВЕРХ"

        return "📉 ВНИЗ"

    @property
    def strength(self) -> str:
        if self.score >= 92:
            return "🔥 VERY HIGH"

        if self.score >= 88:
            return "🟢 HIGH"

        if self.score >= 85:
            return "🟡 GOOD"

        return "⚪ WEAK"
