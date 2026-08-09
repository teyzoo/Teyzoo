from __future__ import annotations
from enum import Enum
class Direction(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
class SignalStatus(str, Enum):
    PENDING = "PENDING"
    WON = "WON"
    LOST = "LOST"
    CANCELLED = "CANCELLED"
class SignalStage(str, Enum):
    WARNING = "WARNING"
    ACTIVE = "ACTIVE"
    FINISHED = "FINISHED"
