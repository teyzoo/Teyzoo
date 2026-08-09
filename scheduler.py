import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot

from config import (
    TIMEZONE,
    SIGNAL_INTERVAL_MINUTES,
)
from database import get_active_users


logger = logging.getLogger(__name__)


async def signal_scheduler(
    bot: Bot,
):

    timezone = ZoneInfo(TIMEZONE)

    while True:

        try:
            now = datetime.now(timezone)

            next_minute = (
                (
                    now.minute
                    // SIGNAL_INTERVAL_MINUTES
                )
                + 1
            ) * SIGNAL_INTERVAL_MINUTES

            next_run = now.replace(
                second=0,
                microsecond=0,
            )

            if next_minute >= 60:
                next_run = (
                    next_run
                    .replace(
                        minute=0
                    )
                    + timedelta(hours=1)
                )
            else:
                next_run = next_run.replace(
                    minute=next_minute
                )

            seconds = (
                next_run - now
            ).total_seconds()

            await asyncio.sleep(
                max(seconds, 1)
            )

            await run_signal_cycle(bot)

        except asyncio.CancelledError:
            raise

        except Exception:
            logger.exception(
                "Ошибка signal scheduler"
            )

            await asyncio.sleep(10)


async def run_signal_cycle(
    bot: Bot,
):

    logger.info(
        "Начинаем новый цикл анализа."
    )

    users = await get_active_users()

    if not users:
        logger.info(
            "Нет активных пользователей."
        )
        return

    # Здесь будет полноценный
    # анализ рынка и выбор лучшего сигнала.

    message = (
        "⛔ <b>NO SIGNAL</b>\n\n"
        "В этом цикле подходящая сделка "
        "не прошла фильтры.\n\n"
        "Следующий анализ через 20 минут."
    )

    for telegram_id in users:

        try:
            await bot.send_message(
                telegram_id,
                message,
                parse_mode="HTML",
            )

        except Exception:
            logger.exception(
                "Не удалось отправить сигнал "
                "пользователю %s",
                telegram_id,
            )
