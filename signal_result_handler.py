from __future__ import annotations

import logging

from aiogram import Bot

from database import (
    get_active_users,
    get_signal,
)


logger = logging.getLogger(
    "signal_result_handler"
)


async def handle_signal_result(
    bot: Bot,
    signal_id: int,
) -> None:

    signal = await get_signal(
        signal_id
    )

    if signal is None:
        logger.warning(
            "Signal #%s not found.",
            signal_id,
        )
        return

    if signal.status not in (
        "WON",
        "LOST",
    ):
        return

    if signal.status == "WON":

        emoji = "🟢"
        title = "WIN"

    else:

        emoji = "🔴"
        title = "LOSS"

    text = (
        f"{emoji} <b>TEYZUS RESULT</b>\n\n"
        f"💱 Пара: "
        f"<b>{signal.symbol}</b>\n"
        f"📊 Направление: "
        f"<b>{signal.direction}</b>\n\n"
        f"🏁 Результат: "
        f"<b>{title}</b>\n\n"
        f"💰 Вход: "
        f"<b>{signal.entry_price}</b>\n"
        f"💰 Выход: "
        f"<b>{signal.exit_price}</b>\n\n"
        f"🎯 Quality Score: "
        f"<b>{signal.score:.1f}%</b>"
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
                "for %s: %s",
                telegram_id,
                exc,
            )
