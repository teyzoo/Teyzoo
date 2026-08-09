from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo
MOSCOW = ZoneInfo(
    "Europe/Moscow"
)
def is_market_session_active(
    value: datetime | None = None,
) -> bool:
    if value is None:
        value = datetime.now(
            MOSCOW
        )
    else:
        value = value.astimezone(
            MOSCOW
        )
    weekday = value.weekday()
    # Суббота и воскресенье.
    if weekday >= 5:
        return False
    hour = value.hour
    # Ночью ликвидность для выбранной
    # стратегии считаем недостаточной.
    if hour < 7:
        return False
    if hour >= 23:
        return False
    return True
def session_name(
    value: datetime | None = None,
) -> str:
    if value is None:
        value = datetime.now(
            MOSCOW
        )
    else:
        value = value.astimezone(
            MOSCOW
        )
    hour = value.hour
    if 7 <= hour < 12:
        return "EUROPE"
    if 12 <= hour < 17:
        return "EUROPE_US"
    if 17 <= hour < 23:
        return "US"
    return "OFF"
