from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


MOSCOW = ZoneInfo(
    "Europe/Moscow"
)


def now_moscow() -> datetime:
    return datetime.now(
        MOSCOW
    )


def next_20_minute_mark(
    now: datetime | None = None,
) -> datetime:

    if now is None:
        now = now_moscow()

    now = now.astimezone(
        MOSCOW
    )

    minute = now.minute

    next_block = (
        (minute // 20) + 1
    ) * 20

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
    close_time: datetime,
) -> datetime:

    return (
        close_time
        - timedelta(minutes=2)
    )


def format_moscow_time(
    value: datetime,
) -> str:

    value = value.astimezone(
        MOSCOW
    )

    return (
        value.strftime("%H:%M")
        + " МСК"
    )


def format_moscow_datetime(
    value: datetime,
) -> str:

    value = value.astimezone(
        MOSCOW
    )

    return value.strftime(
        "%d.%m.%Y %H:%M:%S МСК"
    )
