from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import (
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from database import (
    get_or_create_user,
)


router = Router()

logger = logging.getLogger(
    "handlers.start"
)


def main_keyboard() -> ReplyKeyboardMarkup:

    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="📊 Сигнал"
                ),
                KeyboardButton(
                    text="📈 Последний сигнал"
                ),
            ],
            [
                KeyboardButton(
                    text="📝 Оставить заявку"
                ),
                KeyboardButton(
                    text="ℹ️ Помощь"
                ),
            ],
        ],
        resize_keyboard=True,
    )


@router.message(CommandStart())
async def start_handler(
    message: Message,
):

    if message.from_user is None:
        return

    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    logger.info(
        "User registered: %s",
        user.telegram_id,
    )

    await message.answer(
        (
            "👋 <b>Добро пожаловать в TEYZUS</b>\n\n"
            "🤖 Бот анализирует рынок и "
            "выдаёт только сигналы, которые "
            "прошли заданные фильтры.\n\n"
            "⏱ Новый цикл анализа — каждые 20 минут.\n"
            "⚠️ Предупреждение — за 2 минуты "
            "до расчётного сигнала.\n\n"
            "Важно: сигнал является аналитическим "
            "прогнозом и не гарантирует результат сделки."
        ),
        reply_markup=main_keyboard(),
    )


@router.message(
    lambda message:
        message.text == "ℹ️ Помощь"
)
async def help_handler(
    message: Message,
):

    await message.answer(
        (
            "ℹ️ <b>Как работает TEYZUS</b>\n\n"
            "1. Бот анализирует доступные пары.\n"
            "2. Проверяет несколько таймфреймов.\n"
            "3. Отбрасывает конфликтующие сигналы.\n"
            "4. Проверяет Quality Score.\n"
            "5. Проверяет историческую статистику.\n"
            "6. Только после этого сигнал может "
            "быть отправлен пользователям.\n\n"
            "⏰ В сообщении указывается именно "
            "время закрытия сделки."
        )
    )
