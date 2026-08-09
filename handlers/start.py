from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from database import register_user


router = Router()


@router.message(CommandStart())
async def start_handler(
    message: Message,
):

    user = message.from_user

    if user is None:
        return

    await register_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )

    text = (
        "🚀 <b>TEYZUS SIGNAL</b>\n\n"

        "Бот анализирует рыночные данные "
        "и выдаёт только сигналы, "
        "прошедшие установленные фильтры.\n\n"

        "⏰ Новая проверка — каждые 20 минут.\n"
        "🔔 Предупреждение — за 2 минуты "
        "до расчётного времени сигнала.\n"
        "📊 Результаты автоматически "
        "фиксируются в статистике.\n\n"

        "Команды:\n"
        "/stats — статистика сигналов"
    )

    await message.answer(
        text
    )
