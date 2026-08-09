from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot

from database import (
    get_pending_signals,
    set_signal_entry_price,
    set_signal_result,
)

from market import (
    MarketClient,
    MarketDataError,
)

from time_utils import (
    MOSCOW,
    now_moscow,
)


logger = logging.getLogger(
    "signal_result_checker"
)


# ============================================================
# НАСТРОЙКИ
# ============================================================

CHECK_INTERVAL = 5

PRICE_RETRY_DELAY = 5

MAX_PRICE_RETRIES = 5

RESULT_DELAY_SECONDS = 2

# За сколько секунд до времени закрытия
# можно начать получать цену входа.
ENTRY_PRICE_LOOKBACK_SECONDS = 120


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def parse_close_time(
    value: str,
) -> datetime | None:
    """
    Преобразует строку вида:

        16:20 МСК

    в datetime сегодняшнего дня.

    Также поддерживает:

        16:20

        2026-08-09 16:20

        2026-08-09 16:20 МСК

        ISO datetime.
    """

    if not value:
        return None

    value = value.strip()

    # --------------------------------------------------------
    # Убираем МСК
    # --------------------------------------------------------

    normalized = (
        value
        .replace("МСК", "")
        .strip()
    )

    # --------------------------------------------------------
    # ISO datetime
    # --------------------------------------------------------

    try:

        parsed = datetime.fromisoformat(
            normalized
        )

        if parsed.tzinfo is None:

            parsed = parsed.replace(
                tzinfo=MOSCOW
            )

        else:

            parsed = parsed.astimezone(
                MOSCOW
            )

        return parsed

    except ValueError:
        pass

    # --------------------------------------------------------
    # YYYY-MM-DD HH:MM
    # --------------------------------------------------------

    for fmt in (
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
    ):

        try:

            parsed = datetime.strptime(
                normalized,
                fmt,
            )

            return parsed.replace(
                tzinfo=MOSCOW
            )

        except ValueError:
            continue

    # --------------------------------------------------------
    # HH:MM
    # --------------------------------------------------------

    for fmt in (
        "%H:%M",
        "%H:%M:%S",
    ):

        try:

            parsed_time = datetime.strptime(
                normalized,
                fmt,
            )

            now = now_moscow()

            result = now.replace(
                hour=parsed_time.hour,
                minute=parsed_time.minute,
                second=parsed_time.second,
                microsecond=0,
            )

            # Если время уже прошло,
            # предполагаем следующий день.
            if result < now - timedelta(
                minutes=5
            ):

                result += timedelta(
                    days=1
                )

            return result

        except ValueError:
            continue

    logger.warning(
        "Could not parse close_time: %s",
        value,
    )

    return None


def direction_won(
    direction: str,
    entry_price: float,
    exit_price: float,
) -> bool:

    direction = (
        direction
        .upper()
        .strip()
    )

    if direction == "UP":

        return (
            exit_price
            > entry_price
        )

    if direction == "DOWN":

        return (
            exit_price
            < entry_price
        )

    raise ValueError(
        f"Unknown direction: {direction}"
    )


# ============================================================
# ПОЛУЧЕНИЕ ЦЕНЫ
# ============================================================

async def get_current_price(
    market: MarketClient,
    symbol: str,
) -> float:

    candles = await market.get_candles(
        symbol=symbol,
        timeframe="1m",
        limit=20,
    )

    if not candles:

        raise MarketDataError(
            f"No candles for {symbol}"
        )

    candle = candles[-1]

    return float(
        candle.close
    )


# ============================================================
# ПОЛУЧЕНИЕ ENTRY PRICE
# ============================================================

async def ensure_entry_price(
    market: MarketClient,
    signal,
) -> float | None:

    if signal.entry_price is not None:

        return float(
            signal.entry_price
        )

    try:

        price = await get_current_price(
            market=market,
            symbol=signal.symbol,
        )

    except Exception:

        logger.exception(
            "Could not get entry price "
            "for signal #%s",
            signal.id,
        )

        return None

    saved = await set_signal_entry_price(
        signal_id=signal.id,
        entry_price=price,
    )

    if not saved:

        logger.warning(
            "Could not save entry price "
            "for signal #%s",
            signal.id,
        )

        return None

    logger.info(
        "Signal #%s entry price: %.8f",
        signal.id,
        price,
    )

    return price


# ============================================================
# ОТПРАВКА РЕЗУЛЬТАТА
# ============================================================

async def send_result_to_users(
    bot: Bot,
    signal,
    result: str,
    entry_price: float,
    exit_price: float,
):
    """
    Отправляет результат всем активным
    пользователям.

    Импорт get_active_users сделан
    внутри функции, чтобы не создавать
    циклические зависимости.
    """

    from database import (
        get_active_users,
    )

    users = await get_active_users()

    if not users:

        logger.info(
            "No active users for result."
        )

        return

    if result == "WIN":

        result_text = (
            "🟢 <b>WIN</b>"
        )

    else:

        result_text = (
            "🔴 <b>LOSS</b>"
        )

    direction = (
        signal.direction.upper()
    )

    text = (
        "📊 <b>TEYZUS RESULT</b>\n\n"

        f"💱 Пара: "
        f"<b>{signal.symbol}</b>\n\n"

        f"Направление: "
        f"<b>{direction}</b>\n\n"

        f"💰 Цена входа: "
        f"<b>{entry_price:.8f}</b>\n\n"

        f"💰 Цена закрытия: "
        f"<b>{exit_price:.8f}</b>\n\n"

        f"Результат: "
        f"{result_text}\n\n"

        f"🆔 Signal #{signal.id}"
    )

    for telegram_id in users:

        try:

            await bot.send_message(
                telegram_id,
                text,
                parse_mode="HTML",
            )

        except Exception as exc:

            logger.warning(
                "Result send error "
                "%s: %s",
                telegram_id,
                exc,
            )


# ============================================================
# ПРОВЕРКА ОДНОГО СИГНАЛА
# ============================================================

async def check_signal_result(
    bot: Bot,
    market: MarketClient,
    signal,
) -> bool:
    """
    Проверяет один сигнал.

    Возвращает:

        True  — проверка завершена
        False — пока проверить нельзя
    """

    logger.info(
        "Checking signal #%s (%s)",
        signal.id,
        signal.symbol,
    )

    # --------------------------------------------------------
    # CLOSE TIME
    # --------------------------------------------------------

    close_time = parse_close_time(
        signal.close_time
    )

    if close_time is None:

        logger.error(
            "Invalid close_time for "
            "signal #%s: %s",
            signal.id,
            signal.close_time,
        )

        return False

    now = now_moscow()

    # --------------------------------------------------------
    # ENTRY PRICE
    # --------------------------------------------------------

    entry_price = (
        await ensure_entry_price(
            market=market,
            signal=signal,
        )
    )

    if entry_price is None:

        logger.warning(
            "Entry price unavailable "
            "for signal #%s.",
            signal.id,
        )

        return False

    # --------------------------------------------------------
    # ЕЩЁ НЕ ВРЕМЯ ЗАКРЫТИЯ
    # --------------------------------------------------------

    if now < close_time:

        return False

    # --------------------------------------------------------
    # НЕБОЛЬШАЯ ЗАДЕРЖКА
    # --------------------------------------------------------

    if RESULT_DELAY_SECONDS > 0:

        await asyncio.sleep(
            RESULT_DELAY_SECONDS
        )

    # --------------------------------------------------------
    # ПОЛУЧАЕМ EXIT PRICE
    # --------------------------------------------------------

    exit_price = None

    for attempt in range(
        1,
        MAX_PRICE_RETRIES + 1,
    ):

        try:

            exit_price = (
                await get_current_price(
                    market=market,
                    symbol=signal.symbol,
                )
            )

            break

        except (
            MarketDataError,
            asyncio.TimeoutError,
        ) as exc:

            logger.warning(
                "Exit price attempt "
                "%s/%s failed for "
                "signal #%s: %s",
                attempt,
                MAX_PRICE_RETRIES,
                signal.id,
                exc,
            )

            if attempt < MAX_PRICE_RETRIES:

                await asyncio.sleep(
                    PRICE_RETRY_DELAY
                )

        except Exception:

            logger.exception(
                "Unexpected price error "
                "for signal #%s.",
                signal.id,
            )

            if attempt < MAX_PRICE_RETRIES:

                await asyncio.sleep(
                    PRICE_RETRY_DELAY
                )

    if exit_price is None:

        logger.error(
            "Could not get exit price "
            "for signal #%s.",
            signal.id,
        )

        return False

    # --------------------------------------------------------
    # ОПРЕДЕЛЯЕМ WIN / LOSS
    # --------------------------------------------------------

    try:

        won = direction_won(
            direction=signal.direction,
            entry_price=entry_price,
            exit_price=exit_price,
        )

    except ValueError:

        logger.exception(
            "Invalid direction for "
            "signal #%s.",
            signal.id,
        )

        return False

    result = (
        "WIN"
        if won
        else "LOSS"
    )

    # --------------------------------------------------------
    # СОХРАНЯЕМ РЕЗУЛЬТАТ
    # --------------------------------------------------------

    saved = await set_signal_result(
        signal_id=signal.id,
        result_value=result,
        exit_price=exit_price,
    )

    if not saved:

        logger.error(
            "Could not save result "
            "for signal #%s.",
            signal.id,
        )

        return False

    logger.info(
        "Signal #%s => %s | "
        "entry=%.8f | exit=%.8f",
        signal.id,
        result,
        entry_price,
        exit_price,
    )

    # --------------------------------------------------------
    # ОТПРАВЛЯЕМ РЕЗУЛЬТАТ
    # --------------------------------------------------------

    await send_result_to_users(
        bot=bot,
        signal=signal,
        result=result,
        entry_price=entry_price,
        exit_price=exit_price,
    )

    return True


# ============================================================
# ОСНОВНОЙ ЦИКЛ
# ============================================================

async def run_result_check_cycle(
    bot: Bot,
    market: MarketClient,
):

    try:

        signals = (
            await get_pending_signals()
        )

    except Exception:

        logger.exception(
            "Could not load pending signals."
        )

        return

    if not signals:

        return

    logger.info(
        "Pending signals: %s",
        len(signals),
    )

    for signal in signals:

        try:

            await check_signal_result(
                bot=bot,
                market=market,
                signal=signal,
            )

        except asyncio.CancelledError:

            raise

        except Exception:

            logger.exception(
                "Signal #%s check failed.",
                signal.id,
            )


# ============================================================
# RESULT CHECKER
# ============================================================

async def signal_result_checker(
    bot: Bot,
    market: MarketClient,
):

    logger.info(
        "Signal result checker started."
    )

    while True:

        try:

            await run_result_check_cycle(
                bot=bot,
                market=market,
            )

            await asyncio.sleep(
                CHECK_INTERVAL
            )

        except asyncio.CancelledError:

            logger.info(
                "Signal result checker stopped."
            )

            raise

        except Exception:

            logger.exception(
                "Result checker error."
            )

            await asyncio.sleep(
                CHECK_INTERVAL
            )
