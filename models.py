from __future__ import annotations

from enum import Enum


class Direction(str, Enum):
    UP = "UP"
    DOWN = "DOWN"


class SignalStatus(str, Enum):
    PENDING = "PENDING"
    WIN = "WIN"
    LOSS = "LOSS"
    VOID = "VOID"


class UserStatus(str, Enum):
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
