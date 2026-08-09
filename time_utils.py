from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


# ============================================================
# TIMEZONE
# ============================================================

MOSCOW = ZoneInfo("Europe/Moscow")


# ============================================================
# ОСНОВНЫЕ НАСТРОЙКИ
# ============================================================

# Анализ выполняется каждые 20 минут.
CYCLE_MINUTES = 20

# После анализа сигнал получает следующее
# доступное время закрытия.
#
# Например:
#
# анализ 11:59
# закрытие 12:20
#
# анализ 12:19
# закрытие 12:40
#
# Это специально оставляет запас времени.
CLOSE_AFTER_CYCLES = 1


# ============================================================
# CURRENT MOSCOW TIME
# ============================================================

def now_moscow() -> datetime:
    """
    Возвращает текущее время Москвы
    как timezone-aware datetime.
    """

    return datetime.now(
        MOSCOW
    )


# ============================================================
# NORMALIZE DATETIME
# ============================================================

def ensure_moscow(
    value: datetime,
) -> datetime:
    """
    Приводит datetime к часовому поясу Москвы.

    Если datetime naive, считаем его
    временем Москвы.
    """

    if value.tzinfo is None:

        return value.replace(
            tzinfo=MOSCOW
        )

    return value.astimezone(
        MOSCOW
    )


# ============================================================
# NEXT 20-MINUTE MARK
# ============================================================

def next_20_minute_mark(
    now: datetime | None = None,
) -> datetime:
    """
    Возвращает следующую отметку:

    xx:00
    xx:20
    xx:40

    Например:

    12:01 -> 12:20
    12:19 -> 12:20
    12:20 -> 12:40
    12:41 -> 13:00
    """

    if now is None:

        now = now_moscow()

    now = ensure_moscow(
        now
    )

    # --------------------------------------------------------
    # Сколько минут прошло внутри текущего часа
    # --------------------------------------------------------

    minute = now.minute

    # --------------------------------------------------------
    # Следующий блок
    # --------------------------------------------------------

    next_block = (
        (
            minute
            // CYCLE_MINUTES
        )
        + 1
    ) * CYCLE_MINUTES

    # --------------------------------------------------------
    # Следующий час
    # --------------------------------------------------------

    if next_block >= 60:

        return (
            now.replace(
                minute=0,
                second=0,
                microsecond=0,
            )
            + timedelta(
                hours=1
            )
        )

    # --------------------------------------------------------
    # Следующая отметка текущего часа
    # --------------------------------------------------------

    return now.replace(
        minute=next_block,
        second=0,
        microsecond=0,
    )


# ============================================================
# CURRENT 20-MINUTE MARK
# ============================================================

def current_20_minute_mark(
    now: datetime | None = None,
) -> datetime:
    """
    Возвращает начало текущего 20-минутного блока.

    Например:

    12:03 -> 12:00
    12:19 -> 12:00
    12:20 -> 12:20
    12:39 -> 12:20
    """

    if now is None:

        now = now_moscow()

    now = ensure_moscow(
        now
    )

    block_minute = (
        now.minute
        // CYCLE_MINUTES
    ) * CYCLE_MINUTES

    return now.replace(
        minute=block_minute,
        second=0,
        microsecond=0,
    )


# ============================================================
# NEXT CLOSE TIME
# ============================================================

def next_close_time(
    now: datetime | None = None,
) -> datetime:
    """
    Возвращает время закрытия следующего
    полного 20-минутного интервала.

    Примеры:

    12:01 -> 12:20
    12:20 -> 12:40
    12:35 -> 12:40
    12:59 -> 13:00

    Эта функция используется именно
    для времени ЗАКРЫТИЯ сделки.
    """

    return next_20_minute_mark(
        now
    )


# ============================================================
# CLOSE TIME AFTER ANALYSIS
# ============================================================

def close_time_after_analysis(
    analysis_time: datetime | None = None,
) -> datetime:
    """
    Определяет безопасное время закрытия
    после проведения анализа.

    Если анализ произошёл прямо около
    отметки 20 минут, выбираем следующий
    блок, чтобы не получить практически
    нулевое время до закрытия.

    Примеры:

    11:59:50 -> 12:20
    12:00:05 -> 12:20
    12:19:50 -> 12:20
    12:20:05 -> 12:40
    """

    if analysis_time is None:

        analysis_time = now_moscow()

    analysis_time = ensure_moscow(
        analysis_time
    )

    target = next_20_minute_mark(
        analysis_time
    )

    return target


# ============================================================
# MINUTES UNTIL
# ============================================================

def minutes_until(
    target: datetime,
    now: datetime | None = None,
) -> float:
    """
    Возвращает количество минут
    до указанного времени.
    """

    if now is None:

        now = now_moscow()

    now = ensure_moscow(
        now
    )

    target = ensure_moscow(
        target
    )

    seconds = (
        target - now
    ).total_seconds()

    return max(
        0.0,
        seconds / 60.0,
    )


# ============================================================
# SECONDS UNTIL
# ============================================================

def seconds_until(
    target: datetime,
    now: datetime | None = None,
) -> float:
    """
    Возвращает количество секунд
    до указанного времени.
    """

    if now is None:

        now = now_moscow()

    now = ensure_moscow(
        now
    )

    target = ensure_moscow(
        target
    )

    return max(
        0.0,
        (
            target - now
        ).total_seconds(),
    )


# ============================================================
# FORMAT MOSCOW TIME
# ============================================================

def format_moscow_time(
    value: datetime,
) -> str:
    """
    Формат:

    12:20 МСК
    """

    value = ensure_moscow(
        value
    )

    return (
        value.strftime(
            "%H:%M"
        )
        + " МСК"
    )


# ============================================================
# FORMAT MOSCOW DATETIME
# ============================================================

def format_moscow_datetime(
    value: datetime,
) -> str:
    """
    Формат:

    09.08.2026 12:20 МСК
    """

    value = ensure_moscow(
        value
    )

    return (
        value.strftime(
            "%d.%m.%Y %H:%M"
        )
        + " МСК"
    )


# ============================================================
# IS EXACT 20-MINUTE MARK
# ============================================================

def is_20_minute_mark(
    value: datetime | None = None,
) -> bool:
    """
    Проверяет, является ли время
    отметкой xx:00 / xx:20 / xx:40.
    """

    if value is None:

        value = now_moscow()

    value = ensure_moscow(
        value
    )

    return (
        value.minute
        % CYCLE_MINUTES
        == 0
        and value.second == 0
    )


# ============================================================
# CYCLE INFORMATION
# ============================================================

def get_cycle_info(
    now: datetime | None = None,
) -> dict:

    if now is None:

        now = now_moscow()

    now = ensure_moscow(
        now
    )

    current = (
        current_20_minute_mark(
            now
        )
    )

    next_mark = (
        next_20_minute_mark(
            now
        )
    )

    return {
        "now": now,
        "current_mark": current,
        "next_mark": next_mark,
        "seconds_until_next": (
            seconds_until(
                next_mark,
                now,
            )
        ),
        "minutes_until_next": (
            minutes_until(
                next_mark,
                now,
            )
        ),
    }
