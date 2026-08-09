from __future__ import annotations

from datetime import datetime
from enum import Enum
from zoneinfo import ZoneInfo


MOSCOW = ZoneInfo(
    "Europe/Moscow"
)


class MarketSession(str, Enum):
    ASIA = "ASIA"
    EUROPE = "EUROPE"
    US = "US"
    OVERLAP = "OVERLAP"
    UNKNOWN = "UNKNOWN"


def get_market_session(
    timestamp: datetime | None,
) -> MarketSession:

    if timestamp is None:
        return MarketSession.UNKNOWN

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(
            tzinfo=MOSCOW
        )

    timestamp = timestamp.astimezone(
        MOSCOW
    )

    hour = timestamp.hour

    if 3 <= hour < 10:
        return MarketSession.ASIA

    if 10 <= hour < 16:
        return MarketSession.EUROPE

    if 16 <= hour < 19:
        return MarketSession.OVERLAP

    if 19 <= hour < 24:
        return MarketSession.US

    return MarketSession.UNKNOWN
