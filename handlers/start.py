from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import (
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from database import get_or_create_user


router = Router(name="start")

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
                    text="📈 Статистика"
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
        last_name=message.from_user.last_name,
    )

    logger.info(
        "User registered: %s",
        user.telegram_id,
    )

    await message.answer(
        (
            "👋 <b>Добро пожаловать в TEYZUS</b>\n\n"
            "🤖 Бот анализирует рынок и "
            "выдаёт только сигналы, прошедшие "
            "систему фильтрации.\n\n"
            "⏱ Новый цикл анализа — каждые 20 минут.\n"
            "⚠️ Предупреждение — за 2 минуты "
            "до расчётного времени.\n\n"
            "⚠️ Сигнал является аналитическим "
            "прогнозом и не гарантирует результат сделки."
        ),
        reply_markup=main_keyboard(),
    )


@router.message(
    lambda message: message.text == "ℹ️ Помощь"
)
async def help_handler(
    message: Message,
):
    await message.answer(
        (
            "ℹ️ <b>Как работает TEYZUS</b>\n\n"
            "1. Бот получает рыночные данные.\n"
            "2. Анализирует несколько таймфреймов.\n"
            "3. Сравнивает направления.\n"
            "4. Рассчитывает Quality Score.\n"
            "5. Проверяет policy.\n"
            "6. Сохраняет подтверждённый сигнал.\n"
            "7. Отправляет его пользователям.\n"
            "8. После окончания срока проверяет результат.\n\n"
            "⏰ В сигнале указывается время его закрытия."
        )
    )
