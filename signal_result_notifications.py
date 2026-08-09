from __future__ import annotations

import logging

from aiogram import Bot

from database import (
    get_active_users,
)
from signal_results import (
    SignalCheckResult,
)


logger = logging.getLogger(
    "signal_result_notifications"
)


async def send_result(
    bot: Bot,
    result: SignalCheckResult,
):

    if result.won:

        status = (
            "✅ <b>WIN</b>"
        )

    else:

        status = (
            "❌ <b>LOSS</b>"
        )

    text = (
        "📊 <b>РЕЗУЛЬТАТ СИГНАЛА</b>\n\n"

        f"🆔 Signal #{result.signal_id}\n\n"

        f"{status}\n\n"

        f"💰 Цена входа: "
        f"<b>{result.entry_price}</b>\n"

        f"💰 Цена закрытия: "
        f"<b>{result.exit_price}</b>\n\n"

        f"📌 {result.reason}\n\n"

        "Статистика учитывается "
        "только после фактической "
        "проверки результата."
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
                "Result send error "
                "%s: %s",
                telegram_id,
                exc,
            )
