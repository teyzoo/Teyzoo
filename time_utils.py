from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


MOSCOW = ZoneInfo("Europe/Moscow")


def now_moscow() -> datetime:
    return datetime.now(MOSCOW)


def ensure_moscow(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=MOSCOW)

    return value.astimezone(MOSCOW)


def next_20_minute_mark(
    now: datetime | None = None,
) -> datetime:
    if now is None:
        now = now_moscow()

    now = ensure_moscow(now)

    minute = now.minute

    next_block = ((minute // 20) + 1) * 20

    if next_block >= 60:
        return (
            now.replace(
                minute=0,
                second=0,
                microsecond=0,
            )
            + timedelta(hours=1)
        )

    return now.replace(
        minute=next_block,
        second=0,
        microsecond=0,
    )


def signal_warning_time(
    signal_time: datetime,
    warning_minutes: int = 2,
) -> datetime:
    return (
        ensure_moscow(signal_time)
        - timedelta(minutes=warning_minutes)
    )


def parse_moscow_time(
    value: str,
    reference: datetime | None = None,
) -> datetime:
    """
    Преобразует:

        14:20 МСК
        14:20

    в timezone-aware datetime.

    Если время уже прошло сегодня, предполагается
    следующее наступление этого времени.
    """

    if reference is None:
        reference = now_moscow()

    reference = ensure_moscow(reference)

    raw = value.strip().upper()

    raw = raw.replace("МСК", "").strip()

    parsed = datetime.strptime(
        raw,
        "%H:%M",
    )

    result = reference.replace(
        hour=parsed.hour,
        minute=parsed.minute,
        second=0,
        microsecond=0,
    )

    if result < reference:
        result += timedelta(days=1)

    return result


def format_moscow_time(
    value: datetime,
) -> str:
    value = ensure_moscow(value)

    return value.strftime("%H:%M") + " МСК"
