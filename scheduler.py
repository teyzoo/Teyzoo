from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot
from database import (
    get_active_users,
    save_signal,
)
from market import (
    MarketClient,
    MarketDataError,
)
from market_conditions import (
    evaluate_market_conditions,
)
from pair_selector import (
    PairSelector,
)
from quality_filter import (
    quality_filter,
)
from signal_policy import (
    signal_policy,
)
from time_utils import (
    MOSCOW,
    next_20_minute_mark,
    format_moscow_time,
)
logger = logging.getLogger(
    "scheduler"
)
# ============================================================
# SETTINGS
# ============================================================
MIN_SIGNAL_SCORE = 85.0
MAX_REASONS = 8
# Предупреждение за 2 минуты
WARNING_MINUTES = 2
# ============================================================
# SEND USERS
# ============================================================
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
                "Send error %s: %s",
                telegram_id,
                exc,
            )
# ============================================================
# NO SIGNAL
# ============================================================
async def send_no_signal(
    bot: Bot,
    reason: str,
) -> None:
    await send_to_users(
        bot,
        (
            "⛔ <b>NO SIGNAL</b>\n\n"
            f"{reason}\n\n"
            "❌ Сделка не выдаётся."
        ),
    )
# ============================================================
# WARNING
# ============================================================
async def send_signal_warning(
    bot: Bot,
    symbol: str,
    direction: str,
    signal_time: datetime,
    score: float,
) -> None:
    if direction == "UP":
        direction_text = (
            "📈 <b>ВВЕРХ</b>"
        )
    else:
        direction_text = (
            "📉 <b>ВНИЗ</b>"
        )
    text = (
        "⚠️ <b>TEYZUS — ПРЕДУПРЕЖДЕНИЕ</b>\n\n"
        f"💱 Пара: "
        f"<b>{symbol}</b>\n\n"
        f"{direction_text}\n\n"
        "⏳ <b>Сигнал через 2 минуты</b>\n\n"
        "🕐 Время сигнала: "
        f"<b>"
        f"{format_moscow_time(signal_time)}"
        f"</b>\n\n"
        "🎯 Quality Score: "
        f"<b>{score:.1f}%</b>\n\n"
        "⚠️ Это предварительное "
        "уведомление. Финальный сигнал "
        "будет отправлен в момент входа."
    )
    await send_to_users(
        bot,
        text,
    )
# ============================================================
# RUN ANALYSIS
# ============================================================
async def run_signal_cycle(
    bot: Bot,
    market: MarketClient,
) -> None:
    started_at = datetime.now(
        MOSCOW
    )
    logger.info(
        "===================================="
    )
    logger.info(
        "Starting market analysis."
    )
    logger.info(
        "Analysis time: %s",
        started_at.strftime(
            "%Y-%m-%d %H:%M:%S"
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
            "📡 Актуальные данные рынка недоступны.",
        )
        return
    except asyncio.TimeoutError:
        logger.error(
            "Market request timeout."
        )
        await send_no_signal(
            bot,
            "⏱ Получение рыночных данных превысило таймаут.",
        )
        return
    except Exception:
        logger.exception(
            "Pair selection failed."
        )
        await send_no_signal(
            bot,
            "⚠️ Анализ рынка завершился ошибкой.",
        )
        return
    if best is None:
        await send_no_signal(
            bot,
            (
                "Ни одна доступная пара "
                "не прошла строгую фильтрацию."
            ),
        )
        return
    result = best.result
    if result.direction is None:
        await send_no_signal(
            bot,
            "Нет единого подтверждённого направления.",
        )
        return
    if result.quality_score < MIN_SIGNAL_SCORE:
        await send_no_signal(
            bot,
            (
                "Сигнал не прошёл минимальный "
                "Quality Score.\n\n"
                f"🎯 Score: "
                f"<b>{result.quality_score:.1f}%</b>\n"
                f"🎯 Требуется: "
                f"<b>{MIN_SIGNAL_SCORE:.1f}%</b>"
            ),
        )
        return
    try:
        policy = signal_policy.evaluate(
            result.quality_score
        )
    except Exception:
        logger.exception(
            "Signal policy failed."
        )
        await send_no_signal(
            bot,
            "Не удалось проверить надёжность сигнала.",
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
    # ========================================================
    # SIGNAL TIME
    # ========================================================
    signal_time = next_20_minute_mark(
        started_at
    )
    warning_time = (
        signal_time
        - timedelta(
            minutes=WARNING_MINUTES
        )
    )
    now = datetime.now(
        MOSCOW
    )
    # Если анализ оказался настолько поздним,
    # что 2-минутное окно уже началось,
    # отправляем предупреждение сразу.
    if warning_time <= now:
        await send_signal_warning(
            bot=bot,
            symbol=best.symbol,
            direction=result.direction.value,
            signal_time=signal_time,
            score=result.quality_score,
        )
    else:
        seconds_until_warning = (
            warning_time - now
        ).total_seconds()
        logger.info(
            "Warning scheduled in %.1f seconds.",
            seconds_until_warning,
        )
        try:
            await asyncio.sleep(
                max(
                    1,
                    seconds_until_warning,
                )
            )
        except asyncio.CancelledError:
            raise
        await send_signal_warning(
            bot=bot,
            symbol=best.symbol,
            direction=result.direction.value,
            signal_time=signal_time,
            score=result.quality_score,
        )
    # ========================================================
    # SAVE SIGNAL
    # ========================================================
    historical_probability = (
        policy.historical_probability
    )
    try:
        signal_id = await save_signal(
            symbol=best.symbol,
            direction=result.direction.value,
            score=result.quality_score,
            close_time=format_moscow_time(
                signal_time
            ),
            historical_probability=(
                historical_probability
            ),
        )
    except Exception:
        logger.exception(
            "Could not save signal."
        )
        return
    logger.info(
        "Signal #%s created.",
        signal_id,
    )
    logger.info(
        "Signal time: %s",
        format_moscow_time(
            signal_time
        ),
    )
    logger.info(
        "===================================="
    )
# ============================================================
# SCHEDULER
# ============================================================
async def signal_scheduler(
    bot: Bot,
    market: MarketClient,
) -> None:
    logger.info(
        "Signal scheduler started."
    )
    while True:
        try:
            now = datetime.now(
                MOSCOW
            )
            target = next_20_minute_mark(
                now
            )
            seconds = (
                target - now
            ).total_seconds()
            if seconds < 1:
                seconds = 1
            logger.info(
                "Current Moscow time: %s",
                now.strftime(
                    "%H:%M:%S"
                ),
            )
            logger.info(
                "Next analysis: %s",
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
            logger.info(
                "Signal scheduler stopped."
            )
            raise
        except Exception:
            logger.exception(
                "Scheduler error."
            )
            await asyncio.sleep(
                10
            )
