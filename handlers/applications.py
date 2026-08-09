from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import (
    State,
    StatesGroup,
)
from aiogram.types import (
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from database import save_application


router = Router(
    name="applications"
)


class ApplicationStates(
    StatesGroup
):

    waiting_text = State()


@router.message(
    F.text == "📝 Оставить заявку"
)
async def application_start(
    message: Message,
    state: FSMContext,
):

    await state.set_state(
        ApplicationStates.waiting_text
    )

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="❌ Отмена"
                )
            ]
        ],
        resize_keyboard=True,
    )

    await message.answer(
        "📝 <b>Заявка</b>\n\n"
        "Напишите сообщение, которое "
        "хотите передать владельцу бота.\n\n"
        "Например:\n"
        "• предложение\n"
        "• вопрос\n"
        "• проблема\n"
        "• сотрудничество",
        reply_markup=keyboard,
    )


@router.message(
    ApplicationStates.waiting_text,
    F.text == "❌ Отмена",
)
async def application_cancel(
    message: Message,
    state: FSMContext,
):

    await state.clear()

    await message.answer(
        "❌ Заявка отменена."
    )


@router.message(
    ApplicationStates.waiting_text
)
async def application_receive(
    message: Message,
    state: FSMContext,
):

    if message.from_user is None:
        return

    text = (
        message.text or ""
    ).strip()

    if not text:

        await message.answer(
            "❌ Заявка не может быть пустой."
        )

        return

    if len(text) > 4000:

        await message.answer(
            "❌ Слишком длинная заявка.\n"
            "Максимум — 4000 символов."
        )

        return

    application_id = (
        await save_application(
            telegram_id=(
                message.from_user.id
            ),
            text=text,
        )
    )

    await state.clear()

    await message.answer(
        "✅ <b>Заявка принята.</b>\n\n"
        f"🆔 Номер заявки: "
        f"<b>#{application_id}</b>\n\n"
        "Владелец получит её через "
        "админскую часть бота."
    )
