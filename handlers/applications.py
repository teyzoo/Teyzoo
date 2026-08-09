from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

router = Router()


class ApplicationStates(
    StatesGroup
):

    waiting_for_text = State()


@router.message(
    Command("application")
)
async def application_start(
    message: Message,
    state: FSMContext,
):

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data=(
                        "application_cancel"
                    ),
                )
            ]
        ]
    )

    await state.set_state(
        ApplicationStates.waiting_for_text
    )

    await message.answer(
        "📝 <b>ЗАЯВКА</b>\n\n"
        "Напиши одним сообщением, "
        "что ты хочешь предложить "
        "или какой вопрос хочешь решить.\n\n"
        "После этого заявка будет "
        "сохранена для дальнейшей обработки.",
        reply_markup=keyboard,
    )


@router.callback_query(
    F.data == "application_cancel"
)
async def application_cancel(
    callback: CallbackQuery,
    state: FSMContext,
):

    await state.clear()

    await callback.answer(
        "Заявка отменена."
    )

    if callback.message:
        await callback.message.answer(
            "❌ Заявка отменена."
        )


@router.message(
    ApplicationStates.waiting_for_text
)
async def application_receive(
    message: Message,
    state: FSMContext,
):

    text = (
        message.text
        or message.caption
        or ""
    ).strip()

    if not text:

        await message.answer(
            "❌ Отправь текст заявки."
        )

        return

    await state.update_data(
        application_text=text
    )

    await state.clear()

    await message.answer(
        "✅ <b>ЗАЯВКА ПРИНЯТА</b>\n\n"
        "Твоя заявка сохранена.\n"
        "Администратор сможет обработать "
        "её через панель управления."
    )
