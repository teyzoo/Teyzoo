from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from config import OWNER_ID
from database import (
    get_signal_statistics,
)


router = Router(
    name="admin"
)

logger = logging.getLogger(
    "handlers.admin"
)


def is_owner(
    message: Message,
) -> bool:

    return (
        message.from_user is not None
        and message.from_user.id == OWNER_ID
    )


@router.message(
    Command("admin")
)
async def admin_handler(
    message: Message,
):

    if not is_owner(message):

        await message.answer(
            "⛔ <b>Доступ запрещён.</b>"
        )

        return

    try:

        stats = (
            await get_signal_statistics()
        )

        total = int(
            stats.get(
                "total",
                0,
            )
        )

        wins = int(
            stats.get(
                "wins",
                0,
            )
        )

        losses = int(
            stats.get(
                "losses",
                0,
            )
        )

        pending = int(
            stats.get(
                "pending",
                0,
            )
        )

        winrate = float(
            stats.get(
                "winrate",
                0.0,
            )
        )

        completed = (
            wins + losses
        )

        text = (
            "👑 <b>TEYZUS ADMIN</b>\n\n"
            f"📊 Всего сигналов: "
            f"<b>{total}</b>\n\n"
            f"📁 Завершено: "
            f"<b>{completed}</b>\n"
            f"🟢 WIN: "
            f"<b>{wins}</b>\n"
            f"🔴 LOSS: "
            f"<b>{losses}</b>\n"
            f"⏳ Pending: "
            f"<b>{pending}</b>\n\n"
            f"🎯 WIN RATE: "
            f"<b>{winrate:.2f}%</b>"
        )

        await message.answer(
            text
        )

    except Exception:

        logger.exception(
            "Could not load admin statistics."
        )

        await message.answer(
            (
                "⚠️ <b>Не удалось загрузить "
                "статистику.</b>"
            )
        )
