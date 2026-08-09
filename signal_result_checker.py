from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from aiogram import Bot

from database import (
    get_pending_signals,
    update_signal_result,
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

CHECK_INTERVAL = 10

RESULT_PRICE_TOLERANCE = 0.0


# ============================================================
# ОТПРАВКА
# ============================================================

async def send_result_to_users(
    bot: Bot,
    text: str,
):
    """
    Отправляет результат всем активным пользователям.
    """

    from database import get_active_users

    try:

        users = await get_active_users()

    except Exception:

        logger.exception(
            "Could not get active users."
        )

        return

    for telegram_id in users:

        try:

            await bot.send_message(
                chat_id=telegram_id,
                text=text,
                parse_mode="HTML",
            )

        except Exception as exc:

            logger.warning(
                "Could not send result to %s: %s",
                telegram_id,
                exc,
            )


# ============================================================
# ВСПОМОГАТЕЛЬНОЕ
# ============================================================

def normalize_signal(
    signal: Any,
) -> dict[str, Any]:
    """
    Приводит объект сигнала к обычному dict.

    Поддерживает dict и ORM-подобные объекты.
    """

    if isinstance(signal, dict):

        return signal

    result: dict[str, Any] = {}

    fields = (
        "id",
        "symbol",
        "direction",
        "score",
        "close_time",
        "entry_price",
        "result",
        "status",
        "created_at",
    )

    for field in fields:

        if hasattr(signal, field):

            result[field] = getattr(
                signal,
                field,
            )

    return result


def parse_close_time(
    value: Any,
) -> datetime | None:
    """
    Преобразует время закрытия сигнала
    в datetime Moscow.
    """

    if value is None:
        return None

    if isinstance(
        value,
        datetime,
    ):

        if value.tzinfo is None:

            return value.replace(
                tzinfo=MOSCOW
            )

        return value.astimezone(
            MOSCOW
        )

    if isinstance(
        value,
        str,
    ):

        text = value.strip()

        # Формат:
        # 15:20 МСК
        if text.endswith("МСК"):

            text = text[:-3].strip()

            try:

                parsed = datetime.strptime(
                    text,
                    "%H:%M",
                )

                now = datetime.now(
                    MOSCOW
                )

                return now.replace(
                    hour=parsed.hour,
                    minute=parsed.minute,
                    second=0,
                    microsecond=0,
                )

            except ValueError:

                pass

        # ISO
        try:

            parsed = datetime.fromisoformat(
                text.replace(
                    "Z",
                    "+00:00",
                )
            )

            if parsed.tzinfo is None:

                parsed = parsed.replace(
                    tzinfo=MOSCOW
                )

            return parsed.astimezone(
                MOSCOW
            )

        except ValueError:

            return None

    return None


# ============================================================
# ПОЛУЧЕНИЕ ЦЕНЫ
# ============================================================

async def get_current_price(
    market: MarketClient,
    symbol: str,
) -> float | None:
    """
    Получает последнюю доступную цену.
    """

    try:

        candles = await market.get_candles(
            symbol=symbol,
            timeframe="1m",
            limit=3,
        )

    except MarketDataError as exc:

        logger.warning(
            "Market error for %s: %s",
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

    return float(
        candles[-1].close
    )


# ============================================================
# ОПРЕДЕЛЕНИЕ РЕЗУЛЬТАТА
# ============================================================

def calculate_result(
    direction: str,
    entry_price: float,
    exit_price: float,
) -> str:
    """
    Возвращает WIN или LOSS.

    UP:
        exit > entry = WIN

    DOWN:
        exit < entry = WIN
    """

    direction = (
        direction.upper()
        .strip()
    )

    if direction == "UP":

        if exit_price > (
            entry_price
            + RESULT_PRICE_TOLERANCE
        ):

            return "WIN"

        return "LOSS"

    if direction == "DOWN":

        if exit_price < (
            entry_price
            - RESULT_PRICE_TOLERANCE
        ):

            return "WIN"

        return "LOSS"

    raise ValueError(
        f"Unknown direction: {direction}"
    )


# ============================================================
# ФОРМАТ РЕЗУЛЬТАТА
# ============================================================

def build_result_text(
    signal_id: int,
    symbol: str,
    direction: str,
    entry_price: float,
    exit_price: float,
    result: str,
) -> str:

    if result == "WIN":

        result_text = (
            "🟢 <b>WIN</b>"
        )

        emoji = "🎉"

    else:

        result_text = (
            "🔴 <b>LOSS</b>"
        )

        emoji = "📉"

    if direction.upper() == "UP":

        direction_text = (
            "📈 ВВЕРХ"
        )

    else:

        direction_text = (
            "📉 ВНИЗ"
        )

    return (
        f"{emoji} <b>TEYZUS RESULT</b>\n\n"

        f"🆔 Signal #{signal_id}\n"

        f"💱 Пара: "
        f"<b>{symbol}</b>\n\n"

        f"➡️ Направление: "
        f"<b>{direction_text}</b>\n\n"

        f"💰 Цена входа: "
        f"<b>{entry_price}</b>\n"

        f"💰 Цена закрытия: "
        f"<b>{exit_price}</b>\n\n"

        f"🏆 Результат: "
        f"{result_text}\n\n"

        "⚠️ Результат рассчитан "
        "автоматически по рыночным данным."
    )


# ============================================================
# ПРОВЕРКА ОДНОГО СИГНАЛА
# ============================================================

async def check_signal(
    bot: Bot,
    market: MarketClient,
    signal: Any,
) -> bool:
    """
    Проверяет один сигнал.

    Возвращает True, если результат был установлен.
    """

    data = normalize_signal(
        signal
    )

    signal_id = data.get(
        "id"
    )

    symbol = data.get(
        "symbol"
    )

    direction = data.get(
        "direction"
    )

    close_time = parse_close_time(
        data.get(
            "close_time"
        )
    )

    entry_price = data.get(
        "entry_price"
    )

    # --------------------------------------------------------
    # Проверка данных
    # --------------------------------------------------------

    if signal_id is None:

        logger.warning(
            "Signal without id."
        )

        return False

    if not symbol:

        logger.warning(
            "Signal #%s without symbol.",
            signal_id,
        )

        return False

    if not direction:

        logger.warning(
            "Signal #%s without direction.",
            signal_id,
        )

        return False

    if close_time is None:

        logger.warning(
            "Signal #%s has invalid close time.",
            signal_id,
        )

        return False

    now = datetime.now(
        MOSCOW
    )

    # Сигнал ещё не закрылся.
    if now < close_time:

        return False

    # --------------------------------------------------------
    # Получаем цену
    # --------------------------------------------------------

    exit_price = await get_current_price(
        market=market,
        symbol=symbol,
    )

    if exit_price is None:

        logger.warning(
            "No exit price for signal #%s.",
            signal_id,
        )

        return False

    # --------------------------------------------------------
    # Если entry_price уже сохранён
    # --------------------------------------------------------

    if entry_price is not None:

        try:

            entry_price = float(
                entry_price
            )

        except (
            TypeError,
            ValueError,
        ):

            entry_price = None

    # --------------------------------------------------------
    # Если цена входа отсутствует
    # --------------------------------------------------------

    if entry_price is None:

        logger.warning(
            "Signal #%s has no entry price.",
            signal_id,
        )

        return False

    # --------------------------------------------------------
    # Результат
    # --------------------------------------------------------

    try:

        result = calculate_result(
            direction=direction,
            entry_price=entry_price,
            exit_price=exit_price,
        )

    except Exception:

        logger.exception(
            "Could not calculate result for #%s.",
            signal_id,
        )

        return False

    # --------------------------------------------------------
    # Сохраняем
    # --------------------------------------------------------

    try:

        await update_signal_result(
            signal_id=signal_id,
            result=result,
            exit_price=exit_price,
        )

    except TypeError:

        # Если database.py пока имеет
        # старую сигнатуру.

        try:

            await update_signal_result(
                signal_id,
                result,
                exit_price,
            )

        except Exception:

            logger.exception(
                "Could not update signal #%s.",
                signal_id,
            )

            return False

    except Exception:

        logger.exception(
            "Could not update signal #%s.",
            signal_id,
        )

        return False

    # --------------------------------------------------------
    # Сообщение
    # --------------------------------------------------------

    text = build_result_text(
        signal_id=signal_id,
        symbol=symbol,
        direction=direction,
        entry_price=entry_price,
        exit_price=exit_price,
        result=result,
    )

    await send_result_to_users(
        bot,
        text,
    )

    logger.info(
        "Signal #%s result: %s",
        signal_id,
        result,
    )

    return True


# ============================================================
# ОДИН ЦИКЛ CHECKER
# ============================================================

async def run_result_check_cycle(
    bot: Bot,
    market: MarketClient,
):
    """
    Проверяет все сигналы, которые ожидают результата.
    """

    try:

        signals = await get_pending_signals()

    except Exception:

        logger.exception(
            "Could not get pending signals."
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

            await check_signal(
                bot=bot,
                market=market,
                signal=signal,
            )

        except Exception:

            logger.exception(
                "Unexpected error while checking signal."
            )


# ============================================================
# ПОСТОЯННЫЙ CHECKER
# ============================================================

async def signal_result_checker(
    bot: Bot,
    market: MarketClient,
):
    """
    Бесконечный фоновый цикл проверки результатов.
    """

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
