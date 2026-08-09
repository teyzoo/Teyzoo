from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message

from database import (
    get_latest_signal,
)


router = Router(
    name="signals"
)


@router.message(
    F.text == "📊 Сигнал"
)
async def latest_signal_handler(
    message: Message,
):

    signal = await get_latest_signal()

    if signal is None:

        await message.answer(
            (
                "⛔ <b>Сейчас сигнала нет.</b>\n\n"
                "Бот не будет выдавать сделку, "
                "если она не прошла строгую "
                "фильтрацию."
            )
        )

        return

    direction = (
        "📈 <b>ВВЕРХ</b>"
        if signal.direction == "UP"
        else "📉 <b>ВНИЗ</b>"
    )

    probability = (
        "нет данных"
        if signal.historical_probability is None
        else (
            f"{signal.historical_probability:.1f}%"
        )
    )

    await message.answer(
        (
            "🚨 <b>ПОСЛЕДНИЙ СИГНАЛ</b>\n\n"
            f"💱 Пара: <b>{signal.symbol}</b>\n"
            f"{direction}\n\n"
            f"⏰ Закрыть сделку: "
            f"<b>{signal.close_time}</b>\n\n"
            f"🎯 Quality Score: "
            f"<b>{signal.score:.1f}%</b>\n"
            f"📊 Историческая вероятность: "
            f"<b>{probability}</b>\n\n"
            f"🆔 Signal #{signal.id}\n\n"
            "⚠️ Это аналитический прогноз, "
            "а не гарантия результата."
        )
    )


@router.message(
    F.text == "📈 Статистика"
)
async def statistics_handler(
    message: Message,
):

    from database import (
        get_signal_statistics,
    )

    stats = (
        await get_signal_statistics()
    )

    await message.answer(
        (
            "📊 <b>СТАТИСТИКА</b>\n\n"
            f"Всего проверено: "
            f"<b>{stats.total}</b>\n"
            f"✅ WIN: <b>{stats.wins}</b>\n"
            f"❌ LOSS: <b>{stats.losses}</b>\n"
            f"⏳ Ожидают: <b>{stats.pending}</b>\n\n"
            f"📈 Реальный Win Rate: "
            f"<b>{stats.win_rate:.1f}%</b>\n\n"
            "Процент рассчитывается только "
            "по фактически завершённым сигналам."
        )
    )
