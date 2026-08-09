from __future__ import annotations

import logging

from aiogram import Bot

from database import (
    get_active_users,
)
from time_utils import (
    format_moscow_time,
)


logger = logging.getLogger(
    "signal_notifications"
)


async def send_to_users(
    bot: Bot,
    text: str,
) -> None:

    users = await get_active_users()

    for telegram_id in users:

        try:

            await bot.send_message(
                telegram_id,
                text,
                parse_mode="HTML",
            )

        except Exception as exc:

            logger.warning(
                "Could not send message "
                "to %s: %s",
                telegram_id,
                exc,
            )


async def send_signal_warning(
    bot: Bot,
    signal,
) -> None:

    close_time = format_moscow_time(
        __import__(
            "time_utils"
        ).parse_moscow_time(
            signal.close_time,
            reference=signal.created_at,
        )
    )

    text = (
        "⚠️ <b>TEYZUS WARNING</b>\n\n"
        f"💱 Пара: "
        f"<b>{signal.symbol}</b>\n\n"
        f"🎯 Направление: "
        f"<b>{signal.direction}</b>\n\n"
        f"⏳ <b>Сигнал через 2 минуты.</b>\n"
        f"🕐 Закрытие: <b>{close_time}</b>\n\n"
        "Подготовьтесь к открытию сделки."
    )

    await send_to_users(
        bot,
        text,
    )
