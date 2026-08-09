from __future__ import annotations
import asyncio
import logging
from datetime import datetime
from aiogram import Bot
from database import (
    get_active_users,
    get_signals_for_result_check,
    set_signal_entry_price,
    set_signal_result,
)
from market import (
    MarketClient,
    MarketDataError,
)
from time_utils import (
    MOSCOW,
)
logger = logging.getLogger(
    "signal_result_checker"
)
# ============================================================
# НАСТРОЙКИ
# ============================================================
# Как часто проверяем результаты.
CHECK_INTERVAL = 5
# Допустимое количество последних свечей,
# которое запрашиваем для определения актуальной цены.
PRICE_CANDLE_LIMIT = 5
# ============================================================
# ОТПРАВКА ПОЛЬЗОВАТЕЛЯМ
# ============================================================
async def send_to_users(
    bot: Bot,
    text: str,
) -> None:
    try:
        users = await get_active_users()
    except Exception:
        logger.exception(
            "Could not get active users."
        )
        return
    if not users:
        return
    for telegram_id in users:
        try:
            await bot.send_message(
                telegram_id,
                text,
                parse_mode="HTML",
            )
        except Exception as exc:
            logger.warning(
                "Result message send error "
                "%s: %s",
                telegram_id,
                exc,
            )
# ============================================================
# ПОЛУЧЕНИЕ АКТУАЛЬНОЙ ЦЕНЫ
# ============================================================
async def get_current_price(
    market: MarketClient,
    symbol: str,
) -> float | None:
    try:
        candles = (
            await market.get_candles(
                symbol=symbol,
                timeframe="1m",
                limit=PRICE_CANDLE_LIMIT,
            )
        )
    except MarketDataError as exc:
        logger.warning(
            "Market data error for %s: %s",
            symbol,
            exc,
        )
        return None
    except Exception:
        logger.exception(
            "Could not get price for %s.",
            symbol,
        )
        return None
    if not candles:
        return None
    candle = candles[-1]
    try:
        return float(
            candle.close
        )
    except (
        TypeError,
        ValueError,
    ):
        return None
# ============================================================
# ВРЕМЯ SIGNAL CLOSE_TIME
# ============================================================
def parse_close_time(
    value: str,
) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    # Формат:
    # 14:20 МСК
    if value.endswith(
        " МСК"
    ):
        value = value[:-4].strip()
    try:
        parsed = datetime.strptime(
            value,
            "%H:%M",
        )
    except ValueError:
        return None
    now = datetime.now(
        MOSCOW
    )
    result = now.replace(
        hour=parsed.hour,
        minute=parsed.minute,
        second=0,
        microsecond=0,
    )
    # Если время уже прошло,
    # предполагаем, что оно относится
    # к следующему дню.
    if result < now:
        from datetime import timedelta
        result += timedelta(
            days=1
        )
    return result
# ============================================================
# ОПРЕДЕЛЕНИЕ РЕЗУЛЬТАТА
# ============================================================
def calculate_result(
    direction: str,
    entry_price: float,
    exit_price: float,
) -> str:
    direction = (
        direction.upper().strip()
    )
    # Малейшее изменение цены
    # не должно считаться WIN/LOSS,
    # если цена фактически равна.
    if exit_price == entry_price:
        return "DRAW"
    if direction == "UP":
        if exit_price > entry_price:
            return "WIN"
        return "LOSS"
    if direction == "DOWN":
        if exit_price < entry_price:
            return "WIN"
        return "LOSS"
    raise ValueError(
        f"Unknown direction: {direction}"
    )
# ============================================================
# ФОРМАТ ЦЕНЫ
# ============================================================
def format_price(
    value: float,
) -> str:
    if value >= 1000:
        return f"{value:,.2f}"
    if value >= 1:
        return f"{value:.5f}"
    return f"{value:.8f}"
# ============================================================
# СОХРАНЕНИЕ ENTRY PRICE
# ============================================================
async def process_entry(
    bot: Bot,
    market: MarketClient,
    signal: dict,
) -> None:
    signal_id = signal["id"]
    symbol = signal["symbol"]
    entry_price = await get_current_price(
        market,
        symbol,
    )
    if entry_price is None:
        logger.warning(
            "Could not get entry price "
            "for signal #%s.",
            signal_id,
        )
        return
    saved = await set_signal_entry_price(
        signal_id=signal_id,
        entry_price=entry_price,
        entry_time=datetime.now(
            MOSCOW
        ),
    )
    if not saved:
        logger.warning(
            "Could not save entry price "
            "for signal #%s.",
            signal_id,
        )
        return
    logger.info(
        "Signal #%s entry price: %s",
        signal_id,
        entry_price,
    )
# ============================================================
# ПРОВЕРКА РЕЗУЛЬТАТА
# ============================================================
async def process_result(
    bot: Bot,
    market: MarketClient,
    signal: dict,
) -> None:
    signal_id = signal["id"]
    symbol = signal["symbol"]
    direction = signal["direction"]
    entry_price = signal.get(
        "entry_price"
    )
    if entry_price is None:
        logger.warning(
            "Signal #%s has no entry price. "
            "Trying to create one.",
            signal_id,
        )
        await process_entry(
            bot=bot,
            market=market,
            signal=signal,
        )
        return
    close_time = parse_close_time(
        signal["close_time"]
    )
    if close_time is None:
        logger.error(
            "Invalid close time for "
            "signal #%s: %s",
            signal_id,
            signal["close_time"],
        )
        return
    now = datetime.now(
        MOSCOW
    )
    if now < close_time:
        return
    exit_price = await get_current_price(
        market,
        symbol,
    )
    if exit_price is None:
        logger.warning(
            "Could not get exit price "
            "for signal #%s.",
            signal_id,
        )
        return
    try:
        result = calculate_result(
            direction=direction,
            entry_price=float(
                entry_price
            ),
            exit_price=exit_price,
        )
    except ValueError as exc:
        logger.error(
            "Result calculation error "
            "for signal #%s: %s",
            signal_id,
            exc,
        )
        return
    saved = await set_signal_result(
        signal_id=signal_id,
        result_value=result,
        exit_price=exit_price,
        result_time=datetime.now(
            MOSCOW
        ),
    )
    if not saved:
        logger.warning(
            "Could not save result "
            "for signal #%s.",
            signal_id,
        )
        return
    if result == "WIN":
        result_text = (
            "🟢 <b>WIN</b>"
        )
        emoji = "🟢"
    elif result == "LOSS":
        result_text = (
            "🔴 <b>LOSS</b>"
        )
        emoji = "🔴"
    else:
        result_text = (
            "⚪ <b>DRAW</b>"
        )
        emoji = "⚪"
    text = (
        f"{emoji} <b>TEYZUS RESULT</b>\n\n"
        f"💱 Пара: "
        f"<b>{symbol}</b>\n\n"
        f"📊 Направление: "
        f"<b>{direction}</b>\n\n"
        f"💰 Цена входа: "
        f"<b>"
        f"{format_price(float(entry_price))}"
        f"</b>\n\n"
        f"💰 Цена закрытия: "
        f"<b>"
        f"{format_price(exit_price)}"
        f"</b>\n\n"
        f"🏆 Результат: "
        f"{result_text}\n\n"
        f"🆔 Signal #{signal_id}"
    )
    await send_to_users(
        bot,
        text,
    )
    logger.info(
        "Signal #%s completed: %s",
        signal_id,
        result,
    )
# ============================================================
# ОСНОВНОЙ ЦИКЛ
# ============================================================
async def run_result_check_cycle(
    bot: Bot,
    market: MarketClient,
) -> None:
    try:
        signals = (
            await get_signals_for_result_check()
        )
    except Exception:
        logger.exception(
            "Could not load signals "
            "for result checking."
        )
        return
    if not signals:
        return
    logger.info(
        "Checking %s pending signals.",
        len(signals),
    )
    for signal in signals:
        try:
            signal_id = signal["id"]
            entry_price = signal.get(
                "entry_price"
            )
            close_time = parse_close_time(
                signal["close_time"]
            )
            if close_time is None:
                logger.warning(
                    "Invalid close time "
                    "for signal #%s.",
                    signal_id,
                )
                continue
            now = datetime.now(
                MOSCOW
            )
            # ------------------------------------------------
            # ENTRY
            # ------------------------------------------------
            if (
                entry_price is None
                and now >= close_time
            ):
                await process_entry(
                    bot=bot,
                    market=market,
                    signal=signal,
                )
                # После записи entry_price
                # не проверяем результат
                # в том же цикле.
                continue
            # ------------------------------------------------
            # RESULT
            # ------------------------------------------------
            if (
                entry_price is not None
                and now >= close_time
            ):
                await process_result(
                    bot=bot,
                    market=market,
                    signal=signal,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Error processing signal."
            )
# ============================================================
# SCHEDULER
# ============================================================
async def signal_result_checker(
    bot: Bot,
    market: MarketClient,
) -> None:
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
# ============================================================
# ALIAS
# ============================================================
result_checker = (
    signal_result_checker
)
