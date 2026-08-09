from __future__ import annotations

import logging
from datetime import datetime, timedelta

from aiogram import Bot

from database import (
    get_active_users,
    get_pending_results,
    save_signal_result,
)

from market import (
    MarketClient,
    MarketDataError,
)

from models import Direction

from signal_notifications import (
    SignalNotifier,
)

from signal_result_checker import (
    SignalResultChecker,
    SignalCheck,
    format_result,
)

from time_utils import (
    MOSCOW,
)


logger = logging.getLogger(
    "signal_result_handler"
)


# ============================================================
# НАСТРОЙКИ
# ============================================================

RESULT_TIMEFRAME = "1m"

RESULT_LOOKBACK_CANDLES = 20

# Допустимое отклонение времени проверки.
# Нужно, чтобы scheduler не пропустил сигнал,
# если Render немного задержал выполнение.
RESULT_GRACE_SECONDS = 30


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def parse_close_time(
    value: str,
    now: datetime | None = None,
) -> datetime | None:
    """
    Преобразует:

        19:20 МСК

    в datetime с московской таймзоной.

    Поскольку старая БД хранит только время,
    дата определяется относительно текущего времени.
    """

    if now is None:
        now = datetime.now(MOSCOW)

    now = now.astimezone(MOSCOW)

    if not value:
        return None

    cleaned = value.strip()

    cleaned = cleaned.replace(
        " МСК",
        "",
    )

    cleaned = cleaned.replace(
        "МСК",
        "",
    )

    try:

        parsed_time = datetime.strptime(
            cleaned,
            "%H:%M",
        ).time()

    except ValueError:

        logger.error(
            "Invalid close_time value: %r",
            value,
        )

        return None

    result = now.replace(
        hour=parsed_time.hour,
        minute=parsed_time.minute,
        second=0,
        microsecond=0,
    )

    # Если указанное время уже сильно позади,
    # возможно, это время следующего дня.
    #
    # Например:
    #
    # сейчас 23:59
    # close_time 00:00
    #
    # Значит 00:00 — это завтра.
    if result < now - timedelta(
        minutes=5
    ):

        result += timedelta(
            days=1
        )

    return result


def is_result_ready(
    close_time: datetime,
    now: datetime,
) -> bool:
    """
    Проверяет, наступило ли уже время закрытия.

    Небольшое grace-window позволяет scheduler
    не зависеть от точности запуска ровно в секунду.
    """

    difference = (
        now - close_time
    ).total_seconds()

    return difference >= -RESULT_GRACE_SECONDS


def direction_from_string(
    value: str,
) -> Direction | None:

    normalized = (
        str(value)
        .strip()
        .upper()
    )

    if normalized == "UP":
        return Direction.UP

    if normalized == "DOWN":
        return Direction.DOWN

    return None


# ============================================================
# ФОРМАТ РЕЗУЛЬТАТА
# ============================================================

def format_result_for_users(
    result: SignalCheck,
) -> str:
    """
    Пользовательское сообщение после проверки.
    """

    if result.draw:

        status = (
            "⚪ <b>ВОЗВРАТ</b>"
        )

        status_description = (
            "Цена не изменилась."
        )

    elif result.won:

        status = (
            "🟢 <b>WIN</b>"
        )

        status_description = (
            "Направление сигнала подтвердилось."
        )

    else:

        status = (
            "🔴 <b>LOSS</b>"
        )

        status_description = (
            "Направление сигнала не подтвердилось."
        )

    if result.direction == Direction.UP:

        direction = (
            "📈 ВВЕРХ"
        )

    else:

        direction = (
            "📉 ВНИЗ"
        )

    return (
        "📊 <b>РЕЗУЛЬТАТ СИГНАЛА</b>\n\n"

        f"💱 Пара: "
        f"<b>{result.symbol}</b>\n\n"

        f"{direction}\n\n"

        f"💰 Цена входа: "
        f"<b>{result.entry_price}</b>\n"

        f"💰 Цена закрытия: "
        f"<b>{result.exit_price}</b>\n\n"

        f"{status}\n"

        f"{status_description}\n\n"

        f"🆔 Signal #{result.signal_id}"
    )


# ============================================================
# ПРОВЕРКА ОДНОГО СИГНАЛА
# ============================================================

async def check_one_signal(
    bot: Bot,
    market: MarketClient,
    signal: dict,
) -> bool:
    """
    Проверяет один сигнал.

    Возвращает:

        True  -> обработан
        False -> пока не обработан
    """

    signal_id = int(
        signal["id"]
    )

    symbol = str(
        signal["symbol"]
    )

    direction = direction_from_string(
        str(signal["direction"])
    )

    if direction is None:

        logger.error(
            "Signal #%s has invalid direction: %s",
            signal_id,
            signal["direction"],
        )

        return False

    close_time = parse_close_time(
        str(signal["close_time"])
    )

    if close_time is None:

        logger.error(
            "Signal #%s has invalid close time.",
            signal_id,
        )

        return False

    now = datetime.now(
        MOSCOW
    )

    if not is_result_ready(
        close_time,
        now,
    ):

        return False

    entry_price = signal.get(
        "entry_price"
    )

    if entry_price is None:

        logger.error(
            "Signal #%s has no entry price.",
            signal_id,
        )

        return False

    try:

        entry_price = float(
            entry_price
        )

    except (
        TypeError,
        ValueError,
    ):

        logger.error(
            "Signal #%s has invalid "
            "entry price: %r",
            signal_id,
            entry_price,
        )

        return False

    logger.info(
        "Checking signal #%s: %s %s",
        signal_id,
        symbol,
        direction.value,
    )

    checker = SignalResultChecker(
        market=market
    )

    try:

        result = await checker.check(
            signal_id=signal_id,
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            close_time=close_time,
        )

    except MarketDataError as exc:

        logger.error(
            "Market error for signal #%s: %s",
            signal_id,
            exc,
        )

        return False

    except Exception:

        logger.exception(
            "Unexpected error checking "
            "signal #%s.",
            signal_id,
        )

        return False

    if result is None:

        logger.warning(
            "Signal #%s could not be checked yet.",
            signal_id,
        )

        return False

    if result.draw:

        result_name = "DRAW"

    elif result.won:

        result_name = "WIN"

    else:

        result_name = "LOSS"

    try:

        await save_signal_result(
            signal_id=signal_id,
            result=result_name,
            exit_price=result.exit_price,
        )

    except Exception:

        logger.exception(
            "Could not save result "
            "for signal #%s.",
            signal_id,
        )

        return False

    # --------------------------------------------------------
    # Отправляем результат пользователям
    # --------------------------------------------------------

    try:

        users = await get_active_users()

        if users:

            notifier = SignalNotifier(
                bot
            )

            text = format_result_for_users(
                result
            )

            await notifier.send_result(
                telegram_ids=users,
                text=text,
            )

    except Exception:

        # Результат уже сохранён.
        # Ошибка уведомления не должна
        # заставлять повторно записывать результат.
        logger.exception(
            "Could not send result notification "
            "for signal #%s.",
            signal_id,
        )

    logger.info(
        "Signal #%s finalized as %s.",
        signal_id,
        result_name,
    )

    return True


# ============================================================
# ПРОВЕРКА ВСЕХ ГОТОВЫХ СИГНАЛОВ
# ============================================================

async def check_pending_results(
    bot: Bot,
    market: MarketClient,
) -> int:
    """
    Проверяет все сигналы, которым уже пора
    определить результат.

    Возвращает количество обработанных сигналов.
    """

    try:

        signals = await get_pending_results()

    except Exception:

        logger.exception(
            "Could not load pending results."
        )

        return 0

    if not signals:

        return 0

    logger.info(
        "Pending result checks: %s",
        len(signals),
    )

    processed = 0

    for signal in signals:

        try:

            success = await check_one_signal(
                bot=bot,
                market=market,
                signal=signal,
            )

            if success:
                processed += 1

        except Exception:

            logger.exception(
                "Unhandled error while "
                "processing signal."
            )

    if processed:

        logger.info(
            "Processed %s signal results.",
            processed,
        )

    return processed
