from __future__ import annotations

from aiogram import Bot

from database import (
    get_signal,
)
from signal_notifications import (
    send_to_users,
)


async def notify_signal_result(
    bot: Bot,
    signal_id: int,
) -> None:

    signal = await get_signal(
        signal_id
    )

    if signal is None:
        return

    if signal.status == "WON":

        text = (
            "🟢 <b>СИГНАЛ ЗАКРЫТ — WIN</b>\n\n"
            f"💱 {signal.symbol}\n"
            f"📈 {signal.direction}\n\n"
            f"💰 Вход: "
            f"{signal.entry_price}\n"
            f"💰 Выход: "
            f"{signal.exit_price}\n\n"
            f"🎯 Score: "
            f"{signal.score:.1f}%"
        )

    elif signal.status == "LOST":

        text = (
            "🔴 <b>СИГНАЛ ЗАКРЫТ — LOSS</b>\n\n"
            f"💱 {signal.symbol}\n"
            f"📉 {signal.direction}\n\n"
            f"💰 Вход: "
            f"{signal.entry_price}\n"
            f"💰 Выход: "
            f"{signal.exit_price}\n\n"
            f"🎯 Score: "
            f"{signal.score:.1f}%"
        )

    else:
        return

    await send_to_users(
        bot,
        text,
    )
