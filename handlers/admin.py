from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from config import OWNER_ID
from database import (
    get_signal_statistics,
)


router = Router()


def is_owner(
    message: Message,
) -> bool:

    return (
        message.from_user is not None
        and message.from_user.id == OWNER_ID
    )


@router.message(Command("admin"))
async def admin_handler(
    message: Message,
):

    if not is_owner(message):

        await message.answer(
            "⛔ Доступ запрещён."
        )

        return

    stats = (
        await get_signal_statistics()
    )

    text = (
        "👑 <b>TEYZUS ADMIN</b>\n\n"

        f"📊 Завершено: "
        f"<b>{stats['total']}</b>\n"

        f"🟢 WIN: "
        f"<b>{stats['wins']}</b>\n"

        f"🔴 LOSS: "
        f"<b>{stats['losses']}</b>\n"

        f"⚪ DRAW: "
        f"<b>{stats['draws']}</b>\n"

        f"⏳ Pending: "
        f"<b>{stats['pending']}</b>\n\n"

        f"🎯 WIN RATE: "
        f"<b>{stats['win_rate']:.2f}%</b>"
    )

    await message.answer(
        text
    )
