from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from config import ADMIN_IDS, OWNER_ID
from database import get_signal_statistics


router = Router(name="admin")


def is_admin(
    message: Message,
) -> bool:
    if message.from_user is None:
        return False

    user_id = message.from_user.id

    if OWNER_ID is not None and user_id == OWNER_ID:
        return True

    return user_id in ADMIN_IDS


@router.message(Command("admin"))
async def admin_handler(
    message: Message,
):
    if not is_admin(message):
        await message.answer(
            "⛔ Доступ запрещён."
        )

        return

    stats = await get_signal_statistics()

    await message.answer(
        (
            "👑 <b>TEYZUS ADMIN</b>\n\n"
            f"📊 Всего сигналов: "
            f"<b>{stats['total']}</b>\n"
            f"📦 Завершено: "
            f"<b>{stats['finished']}</b>\n\n"
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
    )
