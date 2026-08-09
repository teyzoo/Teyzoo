from __future__ import annotations

import logging

from aiogram import Bot

from database import (
    get_active_users,
)
from signal_tracker import (
    TrackedSignal,
)


logger = logging.getLogger(
    "signal_notifications"
)


async def send_warning(
    bot: Bot,
    signal: TrackedSignal,
):

    text = (
        "⚠️ <b>ПРЕДУПРЕЖДЕНИЕ</b>\n\n"

        f"💱 Пара: "
        f"<b>{signal.symbol}</b>\n"

        (
            "📈 <b>ВВЕРХ</b>"
            if signal.direction.value == "UP"
            else
            "📉 <b>ВНИЗ</b>"
        )

        + "\n\n"

        "⏰ Сделку закрыть через "
        "<b>2 минуты</b>\n"

        f"🕐 Время закрытия: "
        f"<b>{signal.close_time.strftime('%H:%M')} МСК</b>\n\n"

        "⚠️ Это предварительное "
        "уведомление. "
        "Не открывайте сделку только "
        "на основании этого сообщения."
    )

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
                "Warning send error "
                "%s: %s",
                telegram_id,
                exc,
            )
