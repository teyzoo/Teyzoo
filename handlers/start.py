from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from database import add_user


router = Router()


def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="📊 Получить сигнал"
                ),
            ],
            [
                KeyboardButton(
                    text="🔔 Подписка"
                ),
                KeyboardButton(
                    text="📩 Подать заявку"
                ),
            ],
            [
                KeyboardButton(
                    text="📈 Статистика"
                ),
            ],
        ],
        resize_keyboard=True,
    )


@router.message(CommandStart())
async def start_handler(message: Message):

    user = message.from_user

    if user is None:
        return

    await add_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )

    await message.answer(
        "🤖 <b>TEYZUS SIGNAL</b>\n\n"
        "Бот анализирует рынок и выдаёт "
        "только сигналы, прошедшие фильтры.\n\n"
        "⏰ Проверка — каждые 20 минут.\n"
        "🇷🇺 Время — МСК.\n\n"
        "Если подходящей сделки нет, "
        "бот отправит <b>NO SIGNAL</b>.",
        reply_markup=main_keyboard(),
        parse_mode="HTML",
    )
