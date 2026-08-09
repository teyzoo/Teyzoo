from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import (
    State,
    StatesGroup,
)
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from config import ADMIN_ID
from database import create_application


router = Router()


class ApplicationState(StatesGroup):
    waiting_text = State()


@router.message(
    F.text == "📩 Подать заявку"
)
async def application_start(
    message: Message,
    state: FSMContext,
):

    await state.set_state(
        ApplicationState.waiting_text
    )

    await message.answer(
        "📩 <b>Новая заявка</b>\n\n"
        "Напишите текст вашей заявки одним "
        "сообщением.",
        parse_mode="HTML",
    )


@router.message(
    ApplicationState.waiting_text
)
async def application_receive(
    message: Message,
    state: FSMContext,
):

    user = message.from_user

    if user is None:
        return

    text = message.text or ""

    if not text.strip():
        await message.answer(
            "❌ Заявка не может быть пустой."
        )
        return

    application_id = await create_application(
        telegram_id=user.id,
        username=user.username,
        text=text,
    )

    username = (
        f"@{user.username}"
        if user.username
        else "без username"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ ПРИНЯТЬ",
                    callback_data=(
                        f"app_accept:{application_id}"
                    ),
                ),
                InlineKeyboardButton(
                    text="❌ ОТКЛОНИТЬ",
                    callback_data=(
                        f"app_reject:{application_id}"
                    ),
                ),
            ]
        ]
    )

    await message.bot.send_message(
        ADMIN_ID,
        (
            "📩 <b>НОВАЯ ЗАЯВКА</b>\n\n"
            f"ID заявки: <code>{application_id}</code>\n"
            f"👤 Пользователь: {username}\n"
            f"🆔 ID: <code>{user.id}</code>\n\n"
            f"💬 <b>Заявка:</b>\n{text}"
        ),
        parse_mode="HTML",
        reply_markup=keyboard,
    )

    await state.clear()

    await message.answer(
        "✅ Заявка отправлена.\n\n"
        "Ожидайте решения администратора."
    )
