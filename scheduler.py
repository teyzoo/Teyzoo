from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot

from config import (
    SIGNAL_INTERVAL_MINUTES,
    WARNING_MINUTES,
)

from database import (
    get_active_users,
    save_signal,
)

from market import (
    MarketClient,
    MarketDataError,
)

from pair_selector import PairSelector

from quality_filter import quality_filter

from signal_policy import signal_policy

from time_utils import (
    MOSCOW,
    format_moscow_time,
    next_20_minute_mark,
)


logger = logging.getLogger(
    "scheduler"
)


MAX_REASONS = 8


async def send_to_users(
    bot: Bot,
    text: str,
) -> None:

    users = await get_active_users()

    if not users:
        logger.info(
            "No active users."
        )
        return

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


async def send_warning(
    bot: Bot,
    target: datetime,
) -> None:

    text = (
        "⚠️ <b>ПРЕДУПРЕЖДЕНИЕ</b>\n\n"
        "Через <b>2 минуты</b> будет выполнен "
        "очередной анализ рынка.\n\n"
        f"⏰ Расчётное время сигнала: "
        f"<b>{format_moscow_time(target)}</b>\n\n"
        "📊 Бот сейчас проверит доступные пары "
        "и несколько таймфреймов.\n\n"
        "❗ Направление будет отправлено "
        "только после прохождения фильтров."
    )

    await send_to_users(
        bot,
        text,
    )


async def send_no_signal(
    bot: Bot,
    reason: str,
) -> None:

    text = (
        "⛔ <b>NO SIGNAL</b>\n\n"
        f"{reason}\n\n"
        "❌ Сделка не выдаётся.\n\n"
        "Это сделано специально: если рынок "
        "не даёт достаточно подтверждений, "
        "бот пропускает цикл."
    )

    await send_to_users(
        bot,
        text,
    )


async def run_signal_cycle(
    bot: Bot,
    market: MarketClient,
    target_time: datetime,
) -> None:

    started_at = datetime.now(
        MOSCOW
    )

    logger.info(
        "Starting signal analysis at %s",
        started_at.isoformat(),
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
            "📡 Актуальные рыночные данные "
            "недоступны.",
        )

        return

    except asyncio.TimeoutError:

        logger.error(
            "Market timeout."
        )

        await send_no_signal(
            bot,
            "⏱ Получение рыночных данных "
            "заняло слишком много времени.",
        )

        return

    except Exception:

        logger.exception(
            "Signal analysis failed."
        )

        await send_no_signal(
            bot,
            "⚠️ Во время анализа произошла "
            "техническая ошибка.",
        )

        return

    if best is None:

        logger.info(
            "No pair passed quality filter."
        )

        await send_no_signal(
            bot,
            "Ни одна пара не прошла "
            "строгую фильтрацию.",
        )

        return

    result = best.result

    if result.direction is None:

        await send_no_signal(
            bot,
            "Нет единого подтверждённого "
            "направления.",
        )

        return

    if result.quality_score < 85:

        await send_no_signal(
            bot,
            (
                "Quality Score ниже "
                "минимального порога.\n\n"
                f"Получено: "
                f"<b>{result.quality_score:.1f}%</b>"
            ),
        )

        return

    try:

        policy = signal_policy.evaluate(
            result.quality_score
        )

    except Exception:

        logger.exception(
            "Signal policy error."
        )

        await send_no_signal(
            bot,
            "Не удалось проверить "
            "историческую статистику.",
        )

        return

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

    close_time = target_time

    direction = (
        result.direction.value
    )

    if direction == "UP":

        direction_text = (
            "📈 <b>ВВЕРХ</b>"
        )

    elif direction == "DOWN":

        direction_text = (
            "📉 <b>ВНИЗ</b>"
        )

    else:

        await send_no_signal(
            bot,
            "Получено неизвестное направление.",
        )

        return

    probability = (
        policy.historical_probability
    )

    if probability is None:

        probability_text = (
            "нет достаточной истории"
        )

    else:

        probability_text = (
            f"{probability:.1f}%"
        )

    try:

        signal_id = await save_signal(
            symbol=best.symbol,
            direction=direction,
            score=result.quality_score,
            close_time=(
                format_moscow_time(
                    close_time
                )
            ),
            historical_probability=(
                probability
            ),
        )

    except TypeError:

        signal_id = await save_signal(
            symbol=best.symbol,
            direction=direction,
            score=result.quality_score,
            close_time=(
                format_moscow_time(
                    close_time
                )
            ),
        )

    except Exception:

        logger.exception(
            "Could not save signal."
        )

        await send_no_signal(
            bot,
            "Сигнал не удалось сохранить "
            "в базе данных.",
        )

        return

    reasons_list = (
        result.reasons[:MAX_REASONS]
    )

    if reasons_list:

        reasons = "\n".join(
            f"• {item}"
            for item in reasons_list
        )

    else:

        reasons = (
            "• Подтверждения не указаны."
        )

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
        f"{reasons}\n\n"

        f"🆔 Signal #{signal_id}\n\n"

        "⚠️ Это аналитический прогноз, "
        "а не гарантия результата."
    )

    await send_to_users(
        bot,
        text,
    )

    logger.info(
        "Signal #%s sent.",
        signal_id,
    )


async def wait_until(
    target: datetime,
) -> None:

    while True:

        now = datetime.now(
            MOSCOW
        )

        seconds = (
            target - now
        ).total_seconds()

        if seconds <= 0:
            return

        await asyncio.sleep(
            min(seconds, 10)
        )


async def signal_scheduler(
    bot: Bot,
    market: MarketClient,
) -> None:

    logger.info(
        "Signal scheduler started."
    )

    while True:

        try:

            signal_time = (
                next_20_minute_mark()
            )

            warning_time = (
                signal_time
                - timedelta(
                    minutes=WARNING_MINUTES
                )
            )

            logger.info(
                "Next signal: %s",
                signal_time.strftime(
                    "%H:%M:%S"
                ),
            )

            logger.info(
                "Warning: %s",
                warning_time.strftime(
                    "%H:%M:%S"
                ),
            )

            await wait_until(
                warning_time
            )

            await send_warning(
                bot,
                signal_time,
            )

            await wait_until(
                signal_time
            )

            await run_signal_cycle(
                bot=bot,
                market=market,
                target_time=signal_time,
            )

        except asyncio.CancelledError:

            logger.info(
                "Scheduler stopped."
            )

            raise

        except Exception:

            logger.exception(
                "Scheduler error."
            )

            await asyncio.sleep(
                10
            )
