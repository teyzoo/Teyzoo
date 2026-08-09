from __future__ import annotations

from enum import Enum


class Direction(str, Enum):
    UP = "UP"
    DOWN = "DOWN"


class SignalStatus(str, Enum):
    PENDING = "PENDING"
    WARNING = "WARNING"
    ACTIVE = "ACTIVE"
    FINISHED = "FINISHED"
    CANCELLED = "CANCELLED"


class ApplicationStatus(str, Enum):
    NEW = "NEW"
    IN_PROGRESS = "IN_PROGRESS"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    CLOSED = "CLOSED"
