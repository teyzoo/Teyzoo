from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

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

from probability import (
    refresh_probability,
)

from quality_filter import (
    quality_filter,
)

from signal_policy import (
    signal_policy,
)

from signal_result_checker import (
    SignalResultChecker,
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

WARNING_MINUTES = 2

RESULT_CHECK_INTERVAL = 5


# ============================================================
# SEND USERS
# ============================================================

async def send_to_users(
    bot: Bot,
    text: str,
):

    try:

        users = (
            await get_active_users()
        )

    except Exception:

        logger.exception(
            "Could not get active users."
        )

        return

    if not users:

        logger.info(
            "No active users."
        )

        return

    for telegram_id in users:

        try:

            await bot.send_message(
                chat_id=telegram_id,
                text=text,
                parse_mode="HTML",
            )

        except Exception as exc:

            logger.warning(
                "Could not send message "
                "to %s: %s",
                telegram_id,
                exc,
            )


# ============================================================
# NO SIGNAL
# ============================================================

async def send_no_signal(
    bot: Bot,
    reason: str,
):

    text = (
        "⛔ <b>NO SIGNAL</b>\n\n"
        f"{reason}\n\n"
        "❌ Сделка не выдаётся."
    )

    await send_to_users(
        bot,
        text,
    )


# ============================================================
# WARNING
# ============================================================

async def send_signal_warning(
    bot: Bot,
    symbol: str,
    direction: str,
    close_time: datetime,
    score: float,
):

    if direction == "UP":

        direction_text = (
            "📈 <b>ВВЕРХ</b>"
        )

    elif direction == "DOWN":

        direction_text = (
            "📉 <b>ВНИЗ</b>"
        )

    else:

        direction_text = (
            "❓ <b>НЕОПРЕДЕЛЕНО</b>"
        )

    text = (
        "⚠️ <b>ПРЕДУПРЕЖДЕНИЕ</b>\n\n"

        "Следующий торговый момент "
        "через <b>2 минуты</b>.\n\n"

        f"💱 Пара: <b>{symbol}</b>\n\n"

        f"{direction_text}\n\n"

        "⏰ <b>ЗАКРЫТЬ СДЕЛКУ:</b>\n"
        f"<b>"
        f"{format_moscow_time(close_time)}"
        f"</b>\n\n"

        f"🎯 Quality Score: "
        f"<b>{score:.1f}%</b>\n\n"

        "⚠️ Это предварительное "
        "уведомление. Сигнал может "
        "быть отменён, если финальная "
        "проверка рынка не пройдёт "
        "фильтры."
    )

    await send_to_users(
        bot,
        text,
    )


# ============================================================
# ANALYZE MARKET
# ============================================================

async def analyze_market(
    market: MarketClient,
):

    selector = PairSelector(
        market=market,
        quality_filter=quality_filter,
    )

    return await selector.find_best_pair()


# ============================================================
# RUN SIGNAL CYCLE
# ============================================================

async def run_signal_cycle(
    bot: Bot,
    market: MarketClient,
):

    started_at = datetime.now(
        MOSCOW
    )

    logger.info(
        "================================"
    )

    logger.info(
        "Starting signal analysis: %s",
        started_at.strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
    )

    # ========================================================
    # REFRESH HISTORICAL DATA
    # ========================================================

    try:

        await refresh_probability()

    except Exception:

        logger.exception(
            "Could not refresh probability."
        )

        await send_no_signal(
            bot,
            (
                "Не удалось обновить "
                "историческую статистику."
            ),
        )

        return

    # ========================================================
    # PAIR SELECTION
    # ========================================================

    try:

        best = await analyze_market(
            market
        )

    except MarketDataError as exc:

        logger.error(
            "Market data error: %s",
            exc,
        )

        await send_no_signal(
            bot,
            (
                "📡 Актуальные данные "
                "рынка недоступны."
            ),
        )

        return

    except asyncio.TimeoutError:

        logger.error(
            "Market timeout."
        )

        await send_no_signal(
            bot,
            (
                "⏱ Получение рыночных "
                "данных превысило таймаут."
            ),
        )

        return

    except Exception:

        logger.exception(
            "Market analysis failed."
        )

        await send_no_signal(
            bot,
            (
                "⚠️ Анализ рынка завершился "
                "ошибкой."
            ),
        )

        return

    # ========================================================
    # NO PAIR
    # ========================================================

    if best is None:

        logger.info(
            "No pair passed filters."
        )

        await send_no_signal(
            bot,
            (
                "Ни одна пара не прошла "
                "строгую фильтрацию."
            ),
        )

        return

    result = best.result

    logger.info(
        "Best pair=%s score=%.2f "
        "direction=%s",
        best.symbol,
        result.quality_score,
        result.direction,
    )

    # ========================================================
    # DIRECTION
    # ========================================================

    if result.direction is None:

        await send_no_signal(
            bot,
            "Нет единого подтверждённого направления.",
        )

        return

    # ========================================================
    # SCORE
    # ========================================================

    if (
        result.quality_score
        < MIN_SIGNAL_SCORE
    ):

        await send_no_signal(
            bot,
            (
                "Сигнал не прошёл "
                "минимальный Quality Score.\n\n"
                f"Получено: "
                f"<b>{result.quality_score:.1f}%</b>\n"
                f"Требуется: "
                f"<b>{MIN_SIGNAL_SCORE:.1f}%</b>"
            ),
        )

        return

    # ========================================================
    # POLICY
    # ========================================================

    try:

        policy = (
            signal_policy.evaluate(
                result.quality_score
            )
        )

    except Exception:

        logger.exception(
            "Signal policy failed."
        )

        await send_no_signal(
            bot,
            "Не удалось проверить сигнал.",
        )

        return

    if not policy.allowed:

        logger.info(
            "Signal rejected: %s",
            policy.reason,
        )

        await send_no_signal(
            bot,
            (
                "Сигнал отфильтрован.\n\n"
                f"Причина:\n"
                f"<b>{policy.reason}</b>"
            ),
        )

        return

    # ========================================================
    # CLOSE TIME
    # ========================================================

    close_time = (
        next_20_minute_mark(
            started_at
        )
    )

    # ========================================================
    # DIRECTION
    # ========================================================

    direction = (
        result.direction.value
    )

    if direction not in {
        "UP",
        "DOWN",
    }:

        await send_no_signal(
            bot,
            "Неизвестное направление.",
        )

        return

    # ========================================================
    # ENTRY PRICE
    # ========================================================

    try:

        candles = (
            await market.get_candles(
                symbol=best.symbol,
                timeframe="1m",
                limit=5,
            )
        )

        if not candles:

            await send_no_signal(
                bot,
                "Не удалось получить цену входа.",
            )

            return

        entry_price = float(
            candles[-1].close
        )

    except Exception:

        logger.exception(
            "Could not get entry price."
        )

        await send_no_signal(
            bot,
            "Не удалось получить цену входа.",
        )

        return

    # ========================================================
    # SAVE
    # ========================================================

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
                policy.historical_probability
            ),
            confirmations=(
                result.confirmations
            ),
            total_checks=(
                result.total_checks
            ),
            reasons=(
                result.reasons
            ),
            close_datetime=(
                close_time
            ),
            entry_price=(
                entry_price
            ),
        )

    except TypeError:

        # Совместимость со старой database.py

        logger.warning(
            "Using legacy save_signal()."
        )

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
                policy.historical_probability
            ),
        )

    except Exception:

        logger.exception(
            "Could not save signal."
        )

        await send_no_signal(
            bot,
            "Не удалось сохранить сигнал.",
        )

        return

    # ========================================================
    # REASONS
    # ========================================================

    reasons_list = (
        result.reasons[:MAX_REASONS]
    )

    if reasons_list:

        reasons = "\n".join(
            f"• {reason}"
            for reason in reasons_list
        )

    else:

        reasons = (
            "• Подтверждения отсутствуют."
        )

    # ========================================================
    # PROBABILITY
    # ========================================================

    if (
        policy.historical_probability
        is not None
    ):

        probability_text = (
            f"{policy.historical_probability:.1f}%"
        )

    else:

        probability_text = (
            "недостаточно данных"
        )

    # ========================================================
    # FINAL SIGNAL
    # ========================================================

    if direction == "UP":

        direction_text = (
            "📈 <b>ВВЕРХ</b>"
        )

    else:

        direction_text = (
            "📉 <b>ВНИЗ</b>"
        )

    text = (
        "🚨 <b>TEYZUS SIGNAL</b>\n\n"

        f"💱 Пара: "
        f"<b>{best.symbol}</b>\n\n"

        f"{direction_text}\n\n"

        "⏰ <b>ЗАКРЫТЬ СДЕЛКУ:</b>\n"
        f"<b>"
        f"{format_moscow_time(close_time)}"
        f"</b>\n\n"

        f"💵 Цена сигнала: "
        f"<b>{entry_price}</b>\n\n"

        f"🎯 Quality Score: "
        f"<b>{result.quality_score:.1f}%</b>\n\n"

        f"📊 Историческая вероятность: "
        f"<b>{probability_text}</b>\n\n"

        f"✅ Подтверждений: "
        f"<b>"
        f"{result.confirmations}/"
        f"{result.total_checks}"
        f"</b>\n\n"

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

    logger.info(
        "================================"
    )


# ============================================================
# WARNING CYCLE
# ============================================================

async def run_warning_cycle(
    bot: Bot,
    market: MarketClient,
):

    logger.info(
        "Running 2-minute warning analysis."
    )

    try:

        await refresh_probability()

        best = await analyze_market(
            market
        )

    except Exception:

        logger.exception(
            "Warning analysis failed."
        )

        return

    if best is None:

        logger.info(
            "No pair for warning."
        )

        return

    result = best.result

    if result.direction is None:

        return

    if (
        result.quality_score
        < MIN_SIGNAL_SCORE
    ):

        return

    policy = (
        signal_policy.evaluate(
            result.quality_score
        )
    )

    if not policy.allowed:

        return

    close_time = (
        next_20_minute_mark()
    )

    await send_signal_warning(
        bot=bot,
        symbol=best.symbol,
        direction=(
            result.direction.value
        ),
        close_time=close_time,
        score=result.quality_score,
    )


# ============================================================
# SCHEDULER
# ============================================================

async def signal_scheduler(
    bot: Bot,
    market: MarketClient,
):

    logger.info(
        "Signal scheduler started."
    )

    result_checker = (
        SignalResultChecker(
            market=market,
            interval=RESULT_CHECK_INTERVAL,
        )
    )

    result_checker_task = (
        asyncio.create_task(
            result_checker.run()
        )
    )

    try:

        while True:

            now = datetime.now(
                MOSCOW
            )

            next_signal = (
                next_20_minute_mark(
                    now
                )
            )

            # ------------------------------------------------
            # Время предупреждения:
            #
            # 11:58 -> предупреждение
            # 12:00 -> основной цикл
            # ------------------------------------------------

            warning_time = (
                next_signal
                - __import__(
                    "datetime"
                ).timedelta(
                    minutes=WARNING_MINUTES
                )
            )

            seconds_to_warning = (
                warning_time - now
            ).total_seconds()

            seconds_to_signal = (
                next_signal - now
            ).total_seconds()

            logger.info(
                "Now: %s | Warning: %s | "
                "Signal: %s",
                now.strftime(
                    "%H:%M:%S"
                ),
                warning_time.strftime(
                    "%H:%M:%S"
                ),
                next_signal.strftime(
                    "%H:%M:%S"
                ),
            )

            # =================================================
            # WAIT WARNING
            # =================================================

            if seconds_to_warning > 0:

                await asyncio.sleep(
                    seconds_to_warning
                )

            # =================================================
            # WARNING
            # =================================================

            try:

                await run_warning_cycle(
                    bot=bot,
                    market=market,
                )

            except asyncio.CancelledError:

                raise

            except Exception:

                logger.exception(
                    "Warning cycle failed."
                )

            # =================================================
            # WAIT SIGNAL TIME
            # =================================================

            now = datetime.now(
                MOSCOW
            )

            remaining = (
                next_signal - now
            ).total_seconds()

            if remaining > 0:

                await asyncio.sleep(
                    remaining
                )

            # =================================================
            # MAIN SIGNAL
            # =================================================

            try:

                await run_signal_cycle(
                    bot=bot,
                    market=market,
                )

            except asyncio.CancelledError:

                raise

            except Exception:

                logger.exception(
                    "Signal cycle failed."
                )

                await asyncio.sleep(
                    5
                )

    except asyncio.CancelledError:

        logger.info(
            "Signal scheduler stopped."
        )

        result_checker.stop()

        result_checker_task.cancel()

        try:

            await result_checker_task

        except asyncio.CancelledError:

            pass

        raise

    except Exception:

        logger.exception(
            "Fatal scheduler error."
        )

        result_checker.stop()

        result_checker_task.cancel()

        try:

            await result_checker_task

        except asyncio.CancelledError:

            pass

        raise
