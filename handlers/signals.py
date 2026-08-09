from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message

from database import (
    get_latest_signal,
    get_signal_statistics,
)


router = Router(name="signals")


@router.message(F.text == "📊 Сигнал")
async def latest_signal_handler(
    message: Message,
):
    signal = await get_latest_signal()

    if signal is None:
        await message.answer(
            (
                "⛔ <b>Сейчас сигнала нет.</b>\n\n"
                "Бот не выдаёт сделку, "
                "если она не прошла фильтрацию."
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

    status_text = {
        "PENDING": "⏳ ОЖИДАЕТ",
        "WON": "🟢 WIN",
        "LOST": "🔴 LOSS",
        "CANCELLED": "⚪ ОТМЕНЁН",
    }.get(
        signal.status,
        signal.status,
    )

    await message.answer(
        (
            "🚨 <b>ПОСЛЕДНИЙ СИГНАЛ</b>\n\n"
            f"💱 Пара: <b>{signal.symbol}</b>\n"
            f"{direction}\n\n"
            f"💵 Цена входа: "
            f"<b>{signal.entry_price or '—'}</b>\n"
            f"⏰ Закрыть: "
            f"<b>{signal.close_time}</b>\n"
            f"📌 Статус: <b>{status_text}</b>\n\n"
            f"🎯 Quality Score: "
            f"<b>{signal.score:.1f}%</b>\n"
            f"📊 Историческая вероятность: "
            f"<b>{probability}</b>\n\n"
            f"🆔 Signal #{signal.id}\n\n"
            "⚠️ Аналитический прогноз, "
            "а не гарантия результата."
        )
    )


@router.message(F.text == "📈 Статистика")
async def statistics_handler(
    message: Message,
):
    stats = await get_signal_statistics()

    await message.answer(
        (
            "📊 <b>СТАТИСТИКА TEYZUS</b>\n\n"
            f"Всего сигналов: "
            f"<b>{stats['total']}</b>\n"
            f"Завершено: "
            f"<b>{stats['finished']}</b>\n\n"
            f"🟢 WIN: <b>{stats['wins']}</b>\n"
            f"🔴 LOSS: <b>{stats['losses']}</b>\n"
            f"⚪ DRAW: <b>{stats['draws']}</b>\n"
            f"⏳ Pending: <b>{stats['pending']}</b>\n\n"
            f"📈 Win Rate: "
            f"<b>{stats['win_rate']:.2f}%</b>\n\n"
            "Win Rate рассчитывается только "
            "по завершённым WIN/LOSS сигналам."
        )
    )
