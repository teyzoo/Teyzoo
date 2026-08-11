from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot

from database import get_active_users


logger = logging.getLogger(
    "signal_notifications"
)


async def send_to_users(
    bot: Bot,
    text: str,
) -> int:
    """
    Отправляет сообщение всем активным пользователям.

    Возвращает количество успешных отправок.
    """

    users = await get_active_users()

    sent = 0

    for telegram_id in users:
        try:
            await bot.send_message(
                telegram_id,
                text,
                parse_mode="HTML",
            )
            sent += 1

        except Exception as exc:
            logger.warning(
                "Could not send message to %s: %s",
                telegram_id,
                exc,
            )

    return sent


def _direction_text(
    direction: Any,
) -> tuple[str, str]:
    value = str(
        getattr(
            direction,
            "value",
            direction,
        )
    ).upper()

    if value == "UP":
        return (
            "🟢",
            "ВВЕРХ / CALL",
        )

    if value == "DOWN":
        return (
            "🔴",
            "ВНИЗ / PUT",
        )

    return (
        "⚪",
        "UNKNOWN",
    )


def _format_price(
    value: Any,
) -> str:
    if value is None:
        return "—"

    try:
        return f"{float(value):.6f}"
    except (
        TypeError,
        ValueError,
    ):
        return str(value)


async def send_signal(
    bot: Bot,
    signal,
) -> None:
    emoji, direction = (
        _direction_text(
            signal.direction
        )
    )

    probability = (
        "—"
        if signal.historical_probability
        is None
        else (
            f"{float(signal.historical_probability):.1f}%"
        )
    )

    text = (
        "🚨 <b>TEYZUS SIGNAL</b>\n\n"
        f"💱 <b>Пара:</b> "
        f"<code>{signal.symbol}</code>\n"
        f"{emoji} <b>Направление:</b> "
        f"<b>{direction}</b>\n\n"
        f"💵 <b>Вход:</b> "
        f"<code>{_format_price(signal.entry_price)}</code>\n"
        f"⏰ <b>Расчёт:</b> "
        f"<b>{signal.close_time}</b>\n\n"
        f"🎯 <b>Quality Score:</b> "
        f"<b>{float(signal.score):.1f}%</b>\n"
        f"📊 <b>Историческая вероятность:</b> "
        f"<b>{probability}</b>\n\n"
        f"🆔 <b>Signal #{signal.id}</b>\n\n"
        "⚠️ Аналитический прогноз, "
        "не финансовая гарантия."
    )

    sent = await send_to_users(
        bot,
        text,
    )

    logger.info(
        "Signal notification sent | "
        "signal=%s | users=%s",
        signal.id,
        sent,
    )


async def send_signal_warning(
    bot: Bot,
    signal,
    minutes_left: int = 2,
) -> None:
    emoji, direction = (
        _direction_text(
            signal.direction
        )
    )

    text = (
        "⚠️ <b>TEYZUS WARNING</b>\n\n"
        f"💱 <b>Пара:</b> "
        f"<code>{signal.symbol}</code>\n"
        f"{emoji} <b>Направление:</b> "
        f"<b>{direction}</b>\n\n"
        f"⏰ <b>Расчёт:</b> "
        f"<b>{signal.close_time}</b>\n"
        f"⏳ Осталось около "
        f"<b>{max(0, int(minutes_left))}</b> мин."
    )

    await send_to_users(
        bot,
        text,
    )


async def send_signal_result(
    bot: Bot,
    signal,
) -> None:
    status = str(
        signal.status
    ).upper()

    if status == "WON":
        emoji = "🟢"
        title = "WIN"
    elif status == "LOST":
        emoji = "🔴"
        title = "LOSS"
    elif status == "DRAW":
        emoji = "⚪"
        title = "DRAW"
    else:
        emoji = "⚪"
        title = status

    text = (
        f"{emoji} <b>TEYZUS RESULT</b>\n\n"
        f"💱 <b>Пара:</b> "
        f"<code>{signal.symbol}</code>\n"
        f"📊 <b>Направление:</b> "
        f"<b>{signal.direction}</b>\n\n"
        f"🏁 <b>Результат:</b> "
        f"<b>{title}</b>\n"
        f"🎯 <b>Quality Score:</b> "
        f"<b>{float(signal.score):.1f}%</b>\n\n"
        f"💵 <b>Вход:</b> "
        f"<code>{_format_price(signal.entry_price)}</code>\n"
        f"💵 <b>Выход:</b> "
        f"<code>{_format_price(signal.exit_price)}</code>"
    )

    if getattr(
        signal,
        "result_reason",
        None,
    ):
        text += (
            "\n\n📝 <b>Причина:</b> "
            f"{signal.result_reason}"
        )

    await send_to_users(
        bot,
        text,
    )


__all__ = [
    "send_to_users",
    "send_signal",
    "send_signal_warning",
    "send_signal_result",
]
