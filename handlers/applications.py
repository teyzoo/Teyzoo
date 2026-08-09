from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Text
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import (
    State,
    StatesGroup,
)
from aiogram.types import Message

from database import create_application


router = Router(name="applications")

logger = logging.getLogger(
    "handlers.applications"
)


class ApplicationStates(StatesGroup):
    waiting_text = State()


@router.message(
    Text(text="📝 Оставить заявку")
)
async def application_start(
    message: Message,
    state: FSMContext,
):
    await state.set_state(
        ApplicationStates.waiting_text
    )

    await message.answer(
        (
            "📝 <b>Новая заявка</b>\n\n"
            "Напиши одним сообщением, "
            "что ты хочешь предложить "
            "или какой вопрос хочешь решить.\n\n"
            "Для отмены отправь /cancel."
        )
    )


@router.message(
    ApplicationStates.waiting_text
)
async def application_receive(
    message: Message,
    state: FSMContext,
):
    if message.text == "/cancel":
        await state.clear()

        await message.answer(
            "❌ Заявка отменена."
        )

        return

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
            "❌ Заявка слишком длинная. "
            "Максимум — 4000 символов."
        )

        return

    application_id = await create_application(
        telegram_id=message.from_user.id,
        text=text,
    )

    await state.clear()

    logger.info(
        "Application #%s created by %s",
        application_id,
        message.from_user.id,
    )

    await message.answer(
        (
            "✅ <b>Заявка принята</b>\n\n"
            f"🆔 Номер: <b>#{application_id}</b>\n\n"
            "Мы получили твою заявку."
        )
    )
