from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from database import (
    get_active_users,
    save_signal,
)

from market import (
    market_client,
    MarketDataError,
)

from pair_selector import (
    PairSelector,
)

from quality_filter import (
    quality_filter,
)

from time_utils import (
    next_20_minute_mark,
    format_moscow_time,
)


logger = logging.getLogger(
    __name__
)


async def send_to_users(
    bot: Bot,
    text: str,
):

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
                "Ошибка отправки %s: %s",
                telegram_id,
                exc,
            )


async def run_signal_cycle(
    bot: Bot,
):

    logger.info(
        "Starting signal analysis."
    )

    close_time = (
        next_20_minute_mark()
    )

    try:

        selector = PairSelector(
            market=market_client,
            quality_filter=quality_filter,
        )

        best = (
            await selector.find_best_pair()
        )

    except MarketDataError as exc:

        logger.error(
            "Market data error: %s",
            exc,
        )

        await send_to_users(
            bot,
            (
                "⛔ <b>NO SIGNAL</b>\n\n"
                "Не удалось получить "
                "актуальные рыночные данные.\n\n"
                "❌ Сделка не выдаётся."
            ),
        )

        return

    except Exception:

        logger.exception(
            "Unexpected signal error."
        )

        await send_to_users(
            bot,
            (
                "⛔ <b>NO SIGNAL</b>\n\n"
                "Во время анализа произошла "
                "ошибка.\n\n"
                "❌ Сделка не выдаётся."
            ),
        )

        return

    if best is None:

        await send_to_users(
            bot,
            (
                "⛔ <b>NO SIGNAL</b>\n\n"
                "Ни одна валютная пара "
                "не прошла строгий фильтр.\n\n"
                f"⏰ Следующее время закрытия: "
                f"<b>{format_moscow_time(close_time)}</b>\n\n"
                "❌ Слабые сделки "
                "автоматически отфильтрованы."
            ),
        )

        return

    result = best.result

    if result.direction is None:

        await send_to_users(
            bot,
            (
                "⛔ <b>NO SIGNAL</b>\n\n"
                "Не найдено подтверждённое "
                "направление."
            ),
        )

        return

    if result.direction.value == "UP":

        direction_text = (
            "📈 <b>ВВЕРХ</b>"
        )

    else:

        direction_text = (
            "📉 <b>ВНИЗ</b>"
        )

    signal_id = await save_signal(
        symbol=best.symbol,
        direction=result.direction.value,
        score=result.quality_score,
        close_time=(
            format_moscow_time(
                close_time
            )
        ),
    )

    reasons_text = "\n".join(
        f"• {reason}"
        for reason in result.reasons[:8]
    )

    text = (
        "🚨 <b>TEYZUS SIGNAL</b>\n\n"

        f"💱 Пара: "
        f"<b>{best.symbol}</b>\n\n"

        f"{direction_text}\n\n"

        "⏰ <b>ЗАКРЫТЬ СДЕЛКУ:</b>\n"
        f"<b>{format_moscow_time(close_time)}</b>\n\n"

        f"🔥 Качество сигнала: "
        f"<b>{result.quality_score:.1f}%</b>\n\n"

        f"✅ Подтверждения: "
        f"<b>{result.confirmations}/"
        f"{result.total_checks}</b>\n\n"

        "📊 Подтверждения:\n"
        f"{reasons_text}\n\n"

        f"🆔 Signal #{signal_id}\n\n"

        "⚠️ Процент выше — это "
        "внутренний quality score, "
        "а не гарантированная вероятность "
        "выигрыша."
    )

    await send_to_users(
        bot,
        text,
    )


async def signal_scheduler(
    bot: Bot,
):

    while True:

        try:

            target = (
                next_20_minute_mark()
            )

            now = target.tzinfo

            current = (
                next_20_minute_mark()
            )

            seconds = (
                target - current
            ).total_seconds()

            if seconds <= 0:
                seconds = 1

            logger.info(
                "Next signal cycle: %s",
                target,
            )

            await asyncio.sleep(
                seconds
            )

            await run_signal_cycle(
                bot
            )

        except asyncio.CancelledError:
            raise

        except Exception:

            logger.exception(
                "Scheduler error."
            )

            await asyncio.sleep(
                10
            )
