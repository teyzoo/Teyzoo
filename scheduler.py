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

from signal_monitor import (
    monitor_signals,
)

from signal_tracker import (
    TrackedSignal,
    signal_tracker,
)

from signal_policy import (
    signal_policy,
)

from time_utils import (
    MOSCOW,
    next_20_minute_mark,
    format_moscow_time,
)

from models import Direction


logger = logging.getLogger(
    "scheduler"
)


MIN_SIGNAL_SCORE = 85.0

MAX_REASONS = 8


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
                "Send error %s: %s",
                telegram_id,
                exc,
            )


async def send_no_signal(
    bot: Bot,
    reason: str,
):

    await send_to_users(
        bot,
        (
            "⛔ <b>NO SIGNAL</b>\n\n"
            f"{reason}\n\n"
            "❌ Сделка не выдаётся."
        ),
    )


async def run_signal_cycle(
    bot: Bot,
    market: MarketClient,
):

    started_at = datetime.now(
        MOSCOW
    )

    logger.info(
        "Starting signal cycle at %s",
        started_at.strftime(
            "%H:%M:%S"
        ),
    )

    try:

        selector = PairSelector(
            market=market,
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

        await send_no_signal(
            bot,
            "📡 Данные рынка недоступны.",
        )

        return

    except Exception:

        logger.exception(
            "Pair selection failed."
        )

        await send_no_signal(
            bot,
            "⚠️ Ошибка анализа рынка.",
        )

        return

    if best is None:

        await send_no_signal(
            bot,
            (
                "Ни одна пара не прошла "
                "строгую фильтрацию."
            ),
        )

        return

    result = best.result

    if result.direction is None:

        await send_no_signal(
            bot,
            "Нет подтверждённого направления.",
        )

        return

    if (
        result.quality_score
        < MIN_SIGNAL_SCORE
    ):

        await send_no_signal(
            bot,
            (
                "Quality Score ниже "
                "минимального порога.\n\n"
                f"Получено: "
                f"<b>{result.quality_score:.1f}%</b>\n"
                f"Нужно: "
                f"<b>{MIN_SIGNAL_SCORE:.1f}%</b>"
            ),
        )

        return

    policy = (
        signal_policy.evaluate(
            result.quality_score
        )
    )

    if not policy.allowed:

        await send_no_signal(
            bot,
            (
                "Сигнал отфильтрован.\n\n"
                f"Причина: "
                f"<b>{policy.reason}</b>"
            ),
        )

        return

    close_time = (
        next_20_minute_mark(
            started_at
        )
    )

    if result.direction == Direction.UP:

        direction_text = (
            "📈 <b>ВВЕРХ</b>"
        )

    else:

        direction_text = (
            "📉 <b>ВНИЗ</b>"
        )

    reasons = result.reasons[
        :MAX_REASONS
    ]

    reasons_text = "\n".join(
        f"• {reason}"
        for reason in reasons
    )

    if not reasons_text:
        reasons_text = (
            "• Нет дополнительных причин."
        )

    probability = (
        policy.historical_probability
    )

    probability_text = (
        "недостаточно данных"
        if probability is None
        else f"{probability:.1f}%"
    )

    # ================================================
    # Получаем цену входа
    # ================================================

    try:

        candles = (
            await market.get_candles(
                symbol=best.symbol,
                timeframe="1m",
                limit=5,
            )
        )

        if not candles:
            raise MarketDataError(
                "Нет текущей цены."
            )

        entry_price = candles[-1].close

    except Exception:

        logger.exception(
            "Could not get entry price."
        )

        await send_no_signal(
            bot,
            "Не удалось получить цену входа.",
        )

        return

    # ================================================
    # Сохраняем сигнал
    # ================================================

    try:

        signal_id = await save_signal(
            symbol=best.symbol,
            direction=result.direction.value,
            score=result.quality_score,
            close_time=format_moscow_time(
                close_time
            ),
            historical_probability=probability,
            entry_price=entry_price,
        )

    except TypeError:

        # Совместимость со старой БД.
        signal_id = await save_signal(
            symbol=best.symbol,
            direction=result.direction.value,
            score=result.quality_score,
            close_time=format_moscow_time(
                close_time
            ),
        )

    # ================================================
    # Добавляем сигнал в монитор
    # ================================================

    tracked = TrackedSignal(
        signal_id=signal_id,
        symbol=best.symbol,
        direction=result.direction,
        entry_price=entry_price,
        close_time=close_time,
    )

    await signal_tracker.add(
        tracked
    )

    # ================================================
    # Отправляем сигнал
    # ================================================

    text = (
        "🚨 <b>TEYZUS SIGNAL</b>\n\n"

        f"💱 Пара: "
        f"<b>{best.symbol}</b>\n\n"

        f"{direction_text}\n\n"

        "⏰ <b>ЗАКРЫТЬ СДЕЛКУ:</b>\n"
        f"<b>{format_moscow_time(close_time)}</b>\n\n"

        f"🎯 Quality Score: "
        f"<b>{result.quality_score:.1f}%</b>\n\n"

        f"📊 Историческая вероятность: "
        f"<b>{probability_text}</b>\n\n"

        f"✅ Подтверждений: "
        f"<b>{result.confirmations}/"
        f"{result.total_checks}</b>\n\n"

        "🔎 <b>Подтверждения:</b>\n"
        f"{reasons_text}\n\n"

        f"🆔 Signal #{signal_id}\n\n"

        "⚠️ Это аналитический прогноз. "
        "Гарантии выигрыша нет."
    )

    await send_to_users(
        bot,
        text,
    )

    logger.info(
        "Signal #%s sent.",
        signal_id,
    )


async def signal_scheduler(
    bot: Bot,
    market: MarketClient,
):

    monitor_task = asyncio.create_task(
        monitor_signals(
            bot=bot,
            market=market,
        )
    )

    try:

        logger.info(
            "Signal scheduler started."
        )

        while True:

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
                "Next signal cycle: %s",
                target.strftime(
                    "%H:%M:%S"
                ),
            )

            await asyncio.sleep(
                seconds
            )

            await run_signal_cycle(
                bot=bot,
                market=market,
            )

    except asyncio.CancelledError:

        raise

    finally:

        monitor_task.cancel()

        try:

            await monitor_task

        except asyncio.CancelledError:

            pass
