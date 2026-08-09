from __future__ import annotations

import logging

from aiogram import Bot

from database import get_active_users
from time_utils import format_moscow_time


logger = logging.getLogger(
    "signal_notifications"
)


async def send_to_users(
    bot: Bot,
    text: str,
) -> None:

    users = await get_active_users()

    for telegram_id in users:
        try:
            await bot.send_message(
                telegram_id,
                text,
                parse_mode="HTML",
            )
        except Exception as exc:
            logger.warning(
                "Could not send message to %s: %s",
                telegram_id,
                exc,
            )


async def send_signal(
    bot: Bot,
    signal,
) -> None:

    direction = (
        "📈 ВВЕРХ"
        if signal.direction == "UP"
        else "📉 ВНИЗ"
    )

    probability = (
        "—"
        if signal.historical_probability is None
        else (
            f"{signal.historical_probability:.1f}%"
        )
    )

    text = (
        "🚨 <b>TEYZUS SIGNAL</b>\n\n"
        f"💱 Пара: <b>{signal.symbol}</b>\n"
        f"{direction}\n\n"
        f"💵 Вход: <b>{signal.entry_price:.6f}</b>\n"
        f"⏰ Закрытие: <b>{signal.close_time}</b>\n\n"
        f"🎯 Quality Score: "
        f"<b>{signal.score:.1f}%</b>\n"
        f"📊 Историческая вероятность: "
        f"<b>{probability}</b>\n\n"
        f"🆔 Signal #{signal.id}\n\n"
        "⚠️ Аналитический прогноз, "
        "не финансовая гарантия."
    )

    await send_to_users(
        bot,
        text,
    )


async def send_signal_warning(
    bot: Bot,
    signal,
) -> None:

    text = (
        "⚠️ <b>TEYZUS WARNING</b>\n\n"
        f"💱 Пара: <b>{signal.symbol}</b>\n"
        f"🎯 Направление: <b>{signal.direction}</b>\n\n"
        f"⏰ Закрытие: "
        f"<b>{signal.close_time}</b>\n\n"
        "⏳ До расчётного времени осталось "
        "около 2 минут."
    )

    await send_to_users(
        bot,
        text,
    )


async def send_signal_result(
    bot: Bot,
    signal,
) -> None:

    if signal.status == "WON":
        emoji = "🟢"
        title = "WIN"
    elif signal.status == "LOST":
        emoji = "🔴"
        title = "LOSS"
    else:
        emoji = "⚪"
        title = signal.status

    text = (
        f"{emoji} <b>TEYZUS RESULT</b>\n\n"
        f"💱 Пара: <b>{signal.symbol}</b>\n"
        f"📊 Направление: <b>{signal.direction}</b>\n\n"
        f"🏁 Результат: <b>{title}</b>\n"
        f"🎯 Quality Score: "
        f"<b>{signal.score:.1f}%</b>\n\n"
        f"💵 Вход: "
        f"<b>{signal.entry_price or '—'}</b>\n"
        f"💵 Выход: "
        f"<b>{signal.exit_price or '—'}</b>"
    )

    await send_to_users(
        bot,
        text,
    )
