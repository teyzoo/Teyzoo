from aiogram import Router, F
from aiogram.types import CallbackQuery

from config import ADMIN_ID
from database import (
    get_application,
    update_application,
)


router = Router()


@router.callback_query(
    F.data.startswith("app_accept:")
)
async def accept_application(
    callback: CallbackQuery,
):

    if callback.from_user.id != ADMIN_ID:
        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True,
        )
        return

    application_id = int(
        callback.data.split(":")[1]
    )

    application = await get_application(
        application_id
    )

    if not application:
        await callback.answer(
            "Заявка не найдена.",
            show_alert=True,
        )
        return

    (
        _id,
        telegram_id,
        username,
        text,
        status,
    ) = application

    if status != "pending":
        await callback.answer(
            "Заявка уже обработана.",
            show_alert=True,
        )
        return

    await update_application(
        application_id,
        "accepted",
    )

    await callback.bot.send_message(
        telegram_id,
        "✅ <b>Ваша заявка принята!</b>\n\n"
        "Администратор одобрил заявку.",
        parse_mode="HTML",
    )

    await callback.message.edit_text(
        callback.message.text
        + "\n\n"
        "✅ <b>ЗАЯВКА ПРИНЯТА</b>",
        parse_mode="HTML",
    )

    await callback.answer(
        "Заявка принята."
    )


@router.callback_query(
    F.data.startswith("app_reject:")
)
async def reject_application(
    callback: CallbackQuery,
):

    if callback.from_user.id != ADMIN_ID:
        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True,
        )
        return

    application_id = int(
        callback.data.split(":")[1]
    )

    application = await get_application(
        application_id
    )

    if not application:
        await callback.answer(
            "Заявка не найдена.",
            show_alert=True,
        )
        return

    (
        _id,
        telegram_id,
        username,
        text,
        status,
    ) = application

    if status != "pending":
        await callback.answer(
            "Заявка уже обработана.",
            show_alert=True,
        )
        return

    await update_application(
        application_id,
        "rejected",
    )

    await callback.bot.send_message(
        telegram_id,
        "❌ <b>Ваша заявка отклонена.</b>",
        parse_mode="HTML",
    )

    await callback.message.edit_text(
        callback.message.text
        + "\n\n"
        "❌ <b>ЗАЯВКА ОТКЛОНЕНА</b>",
        parse_mode="HTML",
    )

    await callback.answer(
        "Заявка отклонена."
    )
