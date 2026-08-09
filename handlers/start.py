from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import (
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from database import register_user


logger = logging.getLogger(
    "handlers.start"
)

router = Router(
    name="start"
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
                    text="📨 Подать заявку"
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

    user_id = (
        message.from_user.id
    )

    username = (
        message.from_user.username
    )

    first_name = (
        message.from_user.first_name
        or ""
    )

    try:

        await register_user(
            telegram_id=user_id,
            username=username,
            first_name=first_name,
        )

    except Exception:

        logger.exception(
            "Failed to register user %s",
            user_id,
        )

        await message.answer(
            "⚠️ Не удалось зарегистрировать "
            "профиль. Попробуйте ещё раз."
        )

        return

    await message.answer(
        (
            "👋 <b>Добро пожаловать в TEYZUS</b>\n\n"
            "Бот анализирует рынок и отправляет "
            "только сигналы, прошедшие фильтры.\n\n"
            "⏰ Анализ выполняется каждые 20 минут.\n"
            "⚠️ За 2 минуты до времени сигнала "
            "будет отправлено предупреждение.\n\n"
            "Нажмите «📊 Сигнал», чтобы посмотреть "
            "последний доступный сигнал."
        ),
        reply_markup=main_keyboard(),
    )
