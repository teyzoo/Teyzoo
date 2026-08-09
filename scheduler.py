from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from aiogram import Bot

from database import (
    get_active_users,
    save_signal,
)

from market import (
    MarketClient,
    MarketDataError,
)

from pair_selector import (
    PairSelector,
)

from quality_filter import (
    quality_filter,
)

from time_utils import (
    MOSCOW,
    next_20_minute_mark,
    format_moscow_time,
)


logger = logging.getLogger(
    "scheduler"
)


async def send_to_users(
    bot: Bot,
    text: str,
):

    users = (
        await get_active_users()
    )

    for telegram_id in users:

        try:

            await bot.send_message(
                telegram_id,
                text,
                parse_mode="HTML",
            )

        except Exception as exc:

            logger.warning(
                "Send error %s: %s",
                telegram_id,
                exc,
            )


async def run_signal_cycle(
    bot: Bot,
    market: MarketClient,
):

    logger.info(
        "Starting market analysis."
    )

    try:

        selector = PairSelector(
            market=market,
            quality_filter=(
                quality_filter
            ),
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
                "Актуальные данные рынка "
                "недоступны.\n\n"
                "❌ Сделка не выдаётся."
            ),
        )

        return

    except Exception:

        logger.exception(
            "Signal cycle failed."
        )

        await send_to_users(
            bot,
            (
                "⛔ <b>NO SIGNAL</b>\n\n"
                "Анализ завершился ошибкой.\n\n"
                "❌ Сделка не выдаётся."
            ),
        )

        return

    if best is None:

        await send_to_users(
            bot,
            (
                "⛔ <b>NO SIGNAL</b>\n\n"
                "Ни одна пара не прошла "
                "строгий фильтр."
            ),
        )

        return

    result = best.result

    if result.direction is None:

        await send_to_users(
            bot,
            (
                "⛔ <b>NO SIGNAL</b>\n\n"
                "Нет единого подтверждённого "
                "направления."
            ),
        )

        return

    close_time = (
        next_20_minute_mark()
    )

    if result.direction.value == "UP":

        direction = (
            "📈 <b>ВВЕРХ</b>"
        )

    else:

        direction = (
            "📉 <b>ВНИЗ</b>"
        )

    signal_id = (
        await save_signal(
            symbol=best.symbol,
            direction=(
                result.direction.value
            ),
            score=(
                result.quality_score
            ),
            close_time=(
                format_moscow_time(
                    close_time
                )
            ),
        )
    )

    reasons = "\n".join(
        f"• {reason}"
        for reason in (
            result.reasons[:8]
        )
    )

    text = (
        "🚨 <b>TEYZUS SIGNAL</b>\n\n"

        f"💱 Пара: "
        f"<b>{best.symbol}</b>\n\n"

        f"{direction}\n\n"

        "⏰ <b>ЗАКРЫТЬ СДЕЛКУ:</b>\n"
        f"<b>"
        f"{format_moscow_time(close_time)}"
        f"</b>\n\n"

        f"🎯 Quality score: "
        f"<b>"
        f"{result.quality_score:.1f}%"
        f"</b>\n\n"

        f"✅ Подтверждений: "
        f"<b>"
        f"{result.confirmations}/"
        f"{result.total_checks}"
        f"</b>\n\n"

        "📊 Причины:\n"
        f"{reasons}\n\n"

        f"🆔 Signal #{signal_id}\n\n"

        "⚠️ Quality score не является "
        "гарантией выигрыша."
    )

    await send_to_users(
        bot,
        text,
    )


async def signal_scheduler(
    bot: Bot,
    market: MarketClient,
):

    while True:

        try:

            now = datetime.now(
                MOSCOW
            )

            target = (
                next_20_minute_mark(
                    now
                )
            )

            seconds = (
                target - now
            ).total_seconds()

            if seconds < 1:

                seconds = 1

            logger.info(
                "Next cycle: %s",
                target.strftime(
                    "%H:%M:%S"
                ),
            )

            await asyncio.sleep(
                seconds
            )

            await run_signal_cycle(
                bot,
                market,
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
