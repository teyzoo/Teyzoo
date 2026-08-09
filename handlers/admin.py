from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from config import ADMIN_IDS
from database import (
    get_active_users,
    get_recent_signals,
)


router = Router(
    name="admin"
)


def is_admin(
    telegram_id: int,
) -> bool:

    return telegram_id in ADMIN_IDS


@router.message(
    Command("admin")
)
async def admin_handler(
    message: Message,
):

    if message.from_user is None:
        return

    if not is_admin(
        message.from_user.id
    ):

        await message.answer(
            "⛔ Доступ запрещён."
        )

        return

    users = (
        await get_active_users()
    )

    signals = (
        await get_recent_signals(
            limit=10
        )
    )

    text = (
        "👑 <b>TEYZUS ADMIN</b>\n\n"
        f"👥 Активных пользователей: "
        f"<b>{len(users)}</b>\n"
        f"📊 Последних сигналов: "
        f"<b>{len(signals)}</b>\n\n"
    )

    if signals:

        text += (
            "Последние сигналы:\n\n"
        )

        for signal in signals:

            text += (
                f"#{signal.id} "
                f"{signal.symbol} "
                f"{signal.direction} "
                f"{signal.score:.1f}%\n"
            )

    else:

        text += (
            "Сигналов пока нет."
        )

    await message.answer(
        text
    )
