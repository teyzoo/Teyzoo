from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import (
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from database import register_user


router = Router(
    name="start"
)


def main_keyboard() -> ReplyKeyboardMarkup:

    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="📊 Сигналы"
                ),
            ],
            [
                KeyboardButton(
                    text="📝 Оставить заявку"
                ),
            ],
            [
                KeyboardButton(
                    text="ℹ️ Информация"
                ),
            ],
        ],
        resize_keyboard=True,
    )


@router.message(
    CommandStart()
)
async def start_handler(
    message: Message,
):

    if message.from_user is None:
        return

    await register_user(
        telegram_id=message.from_user.id,
        username=(
            message.from_user.username
        ),
        first_name=(
            message.from_user.first_name
        ),
    )

    text = (
        "👋 <b>Добро пожаловать в TEYZUS</b>\n\n"
        "Бот анализирует рыночные данные "
        "и публикует только сигналы, "
        "которые проходят заданные фильтры.\n\n"
        "⏱ Новый цикл анализа — каждые 20 минут.\n"
        "⚠️ За 2 минуты до сигнала бот "
        "отправляет предупреждение.\n\n"
        "Важно: прогноз не является "
        "гарантией прибыли."
    )

    await message.answer(
        text,
        reply_markup=main_keyboard(),
    )


@router.message(
    lambda message:
    message.text == "ℹ️ Информация"
)
async def information_handler(
    message: Message,
):

    await message.answer(
        "ℹ️ <b>О TEYZUS</b>\n\n"
        "Бот использует технический анализ "
        "рыночных данных.\n\n"
        "Основные проверки:\n"
        "• EMA\n"
        "• RSI\n"
        "• MACD\n"
        "• Bollinger Bands\n"
        "• несколько таймфреймов\n\n"
        "Сигнал может не появиться, если "
        "рынок не проходит строгую фильтрацию.\n\n"
        "Это аналитический инструмент, "
        "а не гарантия результата."
    )
