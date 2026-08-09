from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from database import (
    get_signal_statistics,
)

router = Router()


@router.message(Command("stats"))
async def statistics_handler(
    message: Message,
):

    stats = await get_signal_statistics()

    total = stats["total"]
    wins = stats["wins"]
    losses = stats["losses"]
    draws = stats["draws"]
    pending = stats["pending"]
    win_rate = stats["win_rate"]

    text = (
        "📊 <b>СТАТИСТИКА TEYZUS</b>\n\n"

        f"📌 Всего завершённых: "
        f"<b>{total}</b>\n\n"

        f"🟢 WIN: "
        f"<b>{wins}</b>\n"

        f"🔴 LOSS: "
        f"<b>{losses}</b>\n"

        f"⚪ DRAW: "
        f"<b>{draws}</b>\n\n"

        f"⏳ Ожидают результата: "
        f"<b>{pending}</b>\n\n"

        f"🎯 Фактический WIN RATE: "
        f"<b>{win_rate:.2f}%</b>\n\n"

        "⚠️ Статистика рассчитывается "
        "только по завершённым сигналам."
    )

    await message.answer(
        text
    )
