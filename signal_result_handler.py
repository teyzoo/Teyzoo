from __future__ import annotations

import logging

from aiogram import Bot

from database import (
    get_active_users,
    get_signal,
)
from signal_notifications import (
    send_to_users,
)


logger = logging.getLogger(
    "signal_result_handler"
)


async def handle_signal_result(
    bot: Bot,
    signal_id: int,
) -> None:
    """
    Получает завершённый сигнал и отправляет
    результат пользователям.

    WON / LOST / DRAW поддерживаются явно.
    """

    signal = await get_signal(
        signal_id
    )

    if signal is None:
        logger.warning(
            "Signal #%s not found.",
            signal_id,
        )
        return

    status = str(
        signal.status
    ).upper()

    if status == "WON":
        emoji = "🟢"
        title = "WIN"

    elif status == "LOST":
        emoji = "🔴"
        title = "LOSS"

    elif status == "DRAW":
        emoji = "⚪"
        title = "DRAW"

    elif status == "CANCELLED":
        emoji = "⚪"
        title = "CANCELLED"

    else:
        return

    entry = (
        "—"
        if signal.entry_price is None
        else f"{signal.entry_price:.6f}"
    )

    exit_price = (
        "—"
        if signal.exit_price is None
        else f"{signal.exit_price:.6f}"
    )

    reason = (
        signal.result_reason
        or "Результат рассчитан."
    )

    text = (
        f"{emoji} <b>TEYZUS RESULT</b>\n\n"
        f"💱 <b>Пара:</b> "
        f"<code>{signal.symbol}</code>\n"
        f"📊 <b>Направление:</b> "
        f"<b>{signal.direction}</b>\n\n"
        f"🏁 <b>Результат:</b> "
        f"<b>{title}</b>\n\n"
        f"💰 <b>Вход:</b> "
        f"<code>{entry}</code>\n"
        f"💰 <b>Выход:</b> "
        f"<code>{exit_price}</code>\n\n"
        f"🎯 <b>Quality Score:</b> "
        f"<b>{float(signal.score):.1f}%</b>\n"
        f"📝 <b>Причина:</b> "
        f"{reason}"
    )

    users = await get_active_users()

    sent = 0

    for telegram_id in users:
        try:
            await bot.send_message(
                telegram_id,
                text,
                parse_mode="HTML",
            )
            sent += 1

        except Exception as exc:
            logger.warning(
                "Result send error for %s: %s",
                telegram_id,
                exc,
            )

    logger.info(
        "Result notification sent | "
        "signal=%s | status=%s | users=%s",
        signal_id,
        status,
        sent,
    )


__all__ = [
    "handle_signal_result",
]
