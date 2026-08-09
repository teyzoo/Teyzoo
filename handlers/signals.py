from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import Message

from database import (
    get_signal_statistics,
    get_pending_signals,
)


router = Router(
    name="signals"
)

logger = logging.getLogger(
    "handlers.signals"
)


@router.message(
    F.text == "📈 Последний сигнал"
)
async def latest_signal_handler(
    message: Message,
):
    try:
        pending = await get_pending_signals()

        if not pending:
            await message.answer(
                (
                    "⛔ <b>Сейчас активного сигнала нет.</b>\n\n"
                    "Бот не будет выдавать сделку, "
                    "если она не прошла строгую "
                    "фильтрацию.\n\n"
                    "🔄 Следующий анализ будет выполнен "
                    "в рамках следующего цикла."
                )
            )
            return

        signal = pending[-1]

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

        entry = (
            "не определена"
            if signal.entry_price is None
            else f"{signal.entry_price:g}"
        )

        await message.answer(
            (
                "🚨 <b>АКТИВНЫЙ СИГНАЛ</b>\n\n"
                f"💱 Пара: <b>{signal.symbol}</b>\n"
                f"{direction}\n\n"
                f"💰 Вход: <b>{entry}</b>\n"
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

    except Exception:

        logger.exception(
            "Could not load latest signal."
        )

        await message.answer(
            (
                "⚠️ <b>Не удалось получить сигнал.</b>\n\n"
                "Попробуйте ещё раз через несколько секунд."
            )
        )


@router.message(
    F.text == "📊 Статистика"
)
async def statistics_handler(
    message: Message,
):
    try:

        stats = await get_signal_statistics()

        total = int(
            stats.get(
                "total",
                0,
            )
        )

        wins = int(
            stats.get(
                "wins",
                0,
            )
        )

        losses = int(
            stats.get(
                "losses",
                0,
            )
        )

        pending = int(
            stats.get(
                "pending",
                0,
            )
        )

        winrate = float(
            stats.get(
                "winrate",
                0.0,
            )
        )

        await message.answer(
            (
                "📊 <b>СТАТИСТИКА TEYZUS</b>\n\n"
                f"Всего сигналов: "
                f"<b>{total}</b>\n\n"
                f"🟢 WIN: <b>{wins}</b>\n"
                f"🔴 LOSS: <b>{losses}</b>\n"
                f"⏳ Ожидают: <b>{pending}</b>\n\n"
                f"📈 Win Rate: "
                f"<b>{winrate:.1f}%</b>\n\n"
                "Win Rate рассчитывается только "
                "по завершённым сигналам."
            )
        )

    except Exception:

        logger.exception(
            "Could not load signal statistics."
        )

        await message.answer(
            (
                "⚠️ <b>Не удалось получить статистику.</b>\n\n"
                "Попробуйте ещё раз позже."
            )
        )
