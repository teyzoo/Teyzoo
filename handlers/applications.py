from __future__ import annotations

from aiogram import F, Router
from aiogram.types import (
    Message,
)

router = Router(
    name="applications"
)


@router.message(
    F.text == "📨 Подать заявку"
)
async def application_start(
    message: Message,
):

    await message.answer(
        (
            "📨 <b>Заявка</b>\n\n"
            "Напишите одним сообщением:\n\n"
            "1. Ваш Telegram username\n"
            "2. Что вы хотите предложить\n"
            "3. Дополнительную информацию\n\n"
            "Заявка будет передана администрации."
        )
    )
