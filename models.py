from __future__ import annotations

from enum import Enum


class Direction(str, Enum):

    UP = "UP"

    DOWN = "DOWN"


class SignalStatus(str, Enum):

    WAITING = "WAITING"

    ACTIVE = "ACTIVE"

    WON = "WON"

    LOST = "LOST"

    CANCELLED = "CANCELLED"


class ApplicationStatus(str, Enum):

    NEW = "NEW"

    ACCEPTED = "ACCEPTED"

    REJECTED = "REJECTED"

    COMPLETED = "COMPLETED"
