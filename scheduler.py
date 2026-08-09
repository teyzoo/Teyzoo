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
from pair_selector import (
    PairSelector,
)
from market_conditions import (
    evaluate_market_conditions,
)
from signal_policy import (
    signal_policy,
)
from time_utils import (
    MOSCOW,
    next_20_minute_mark,
    format_moscow_time,
)
from quality_filter import (
    quality_filter,
)
from signal_result_checker import (
    result_checker_loop,
)
logger = logging.getLogger("scheduler")
# ============================================================
# НАСТРОЙКИ
# ============================================================
MIN_SIGNAL_SCORE = 85.0
MAX_REASONS = 8
# Предупреждение отправляется за 2 минуты
# до момента выдачи сигнала.
WARNING_MINUTES = 2
# ============================================================
# ОТПРАВКА ПОЛЬЗОВАТЕЛЯМ
# ============================================================
async def send_to_users(
    bot: Bot,
    text: str,
):
    users = await get_active_users()
    if not users:
        logger.info("No active users.")
        return
    logger.info(
        "Sending message to %s users.",
        len(users),
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
# ПРЕДУПРЕЖДЕНИЕ
# ============================================================
async def send_signal_warning(
    bot: Bot,
    target: datetime,
):
    """
    Предупреждение за 2 минуты
    до очередного анализа.
    Важно:
    это НЕ сигнал на вход.
    Это только уведомление пользователя,
    что через 2 минуты будет проверка.
    """
    text = (
        "⚠️ <b>TEYZUS — ПРЕДУПРЕЖДЕНИЕ</b>\n\n"
        "Через <b>2 минуты</b> будет выполнен "
        "очередной анализ рынка.\n\n"
        f"⏰ Время анализа: "
        f"<b>{format_moscow_time(target)}</b>\n\n"
        "📊 Если рынок пройдёт все фильтры, "
        "бот отправит торговый сигнал.\n\n"
        "❗ Сейчас сигнал ещё НЕ выдан."
    )
    await send_to_users(
        bot,
        text,
    )
# ============================================================
# АНАЛИЗ ОДНОГО ЦИКЛА
# ============================================================
async def run_signal_cycle(
    bot: Bot,
    market: MarketClient,
):
    started_at = datetime.now(MOSCOW)
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
    # --------------------------------------------------------
    # 1. PairSelector
    # --------------------------------------------------------
    try:
        selector = PairSelector(
            market=market,
            quality_filter=quality_filter,
        )
    except Exception:
        logger.exception(
            "Could not create PairSelector."
        )
        await send_no_signal(
            bot,
            "⚠️ Не удалось запустить анализ рынка.",
        )
        return
    # --------------------------------------------------------
    # 2. Поиск лучшей пары
    # --------------------------------------------------------
    try:
        best = await selector.find_best_pair()
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
    # --------------------------------------------------------
    # 3. Нет пары
    # --------------------------------------------------------
    if best is None:
        logger.info(
            "No pair passed filters."
        )
        await send_no_signal(
            bot,
            (
                "Ни одна доступная пара "
                "не прошла строгую фильтрацию."
            ),
        )
        return
    logger.info(
        "Best pair: %s",
        best.symbol,
    )
    result = best.result
    logger.info(
        "Direction: %s",
        result.direction,
    )
    logger.info(
        "Quality score: %.2f",
        result.quality_score,
    )
    logger.info(
        "Confirmations: %s/%s",
        result.confirmations,
        result.total_checks,
    )
    # --------------------------------------------------------
    # 4. Направление
    # --------------------------------------------------------
    if result.direction is None:
        await send_no_signal(
            bot,
            "Нет единого подтверждённого направления.",
        )
        return
    # --------------------------------------------------------
    # 5. Quality Score
    # --------------------------------------------------------
    if result.quality_score < MIN_SIGNAL_SCORE:
        logger.info(
            "Rejected by score: %.2f",
            result.quality_score,
        )
        await send_no_signal(
            bot,
            (
                "Сигнал не прошёл минимальный "
                "Quality Score.\n\n"
                f"🎯 Текущий score: "
                f"<b>{result.quality_score:.1f}%</b>\n"
                f"🎯 Требуется: "
                f"<b>{MIN_SIGNAL_SCORE:.1f}%</b>"
            ),
        )
        return
    # --------------------------------------------------------
    # 6. Signal Policy
    # --------------------------------------------------------
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
        logger.info(
            "Rejected by policy: %s",
            policy.reason,
        )
        await send_no_signal(
            bot,
            (
                "Сигнал отфильтрован.\n\n"
                f"Причина: "
                f"<b>{policy.reason}</b>"
            ),
        )
        return
    # --------------------------------------------------------
    # 7. Время закрытия
    # --------------------------------------------------------
    close_time = next_20_minute_mark(
        started_at
    )
    # --------------------------------------------------------
    # 8. Направление
    # --------------------------------------------------------
    if result.direction.value == "UP":
        direction_text = "📈 <b>ВВЕРХ</b>"
    elif result.direction.value == "DOWN":
        direction_text = "📉 <b>ВНИЗ</b>"
    else:
        await send_no_signal(
            bot,
            "Неизвестное направление сигнала.",
        )
        return
    # --------------------------------------------------------
    # 9. Historical probability
    # --------------------------------------------------------
    historical_probability = getattr(
        policy,
        "historical_probability",
        None,
    )
    if historical_probability is not None:
        probability_text = (
            f"{historical_probability:.1f}%"
        )
    else:
        probability_text = (
            "недостаточно данных"
        )
    # --------------------------------------------------------
    # 10. Сохраняем сигнал
    # --------------------------------------------------------
    try:
        signal_id = await save_signal(
            symbol=best.symbol,
            direction=result.direction.value,
            score=result.quality_score,
            close_time=format_moscow_time(
                close_time
            ),
            historical_probability=(
                historical_probability
            ),
        )
    except TypeError:
        logger.warning(
            "Using legacy save_signal()."
        )
        signal_id = await save_signal(
            symbol=best.symbol,
            direction=result.direction.value,
            score=result.quality_score,
            close_time=format_moscow_time(
                close_time
            ),
        )
    except Exception:
        logger.exception(
            "Could not save signal."
        )
        await send_no_signal(
            bot,
            "Не удалось сохранить сигнал в базе данных.",
        )
        return
    # --------------------------------------------------------
    # 11. Причины
    # --------------------------------------------------------
    reasons_list = result.reasons[:MAX_REASONS]
    if reasons_list:
        reasons = "\n".join(
            f"• {reason}"
            for reason in reasons_list
        )
    else:
        reasons = "• Подтверждения не указаны."
    # --------------------------------------------------------
    # 12. Сообщение
    # --------------------------------------------------------
    text = (
        "🚨 <b>TEYZUS SIGNAL</b>\n\n"
        f"💱 Пара: <b>{best.symbol}</b>\n\n"
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
        "⚠️ Сигнал является аналитическим "
        "прогнозом. Quality Score не означает "
        "гарантированный выигрыш."
    )
    # --------------------------------------------------------
    # 13. Отправляем сигнал
    # --------------------------------------------------------
    await send_to_users(
        bot,
        text,
    )
    logger.info(
        "Signal #%s sent.",
        signal_id,
    )
    logger.info(
        "===================================="
    )
# ============================================================
# ОСНОВНОЙ SCHEDULER
# ============================================================
async def signal_scheduler(
    bot: Bot,
    market: MarketClient,
):
    """
    Основной планировщик.
    Каждые 20 минут:
        T - 2 минуты
            ↓
        WARNING
        T
            ↓
        MARKET ANALYSIS
        после закрытия
            ↓
        RESULT CHECKER
    """
    logger.info(
        "Signal scheduler started."
    )
    # --------------------------------------------------------
    # Отдельная задача проверки результатов
    # --------------------------------------------------------
    checker_task = asyncio.create_task(
        result_checker_loop(bot)
    )
    try:
        while True:
            try:
                now = datetime.now(
                    MOSCOW
                )
                target = next_20_minute_mark(
                    now
                )
                warning_time = (
                    target
                    - timedelta(
                        minutes=WARNING_MINUTES
                    )
                )
                # --------------------------------------------
                # Если предупреждение ещё впереди
                # --------------------------------------------
                seconds_to_warning = (
                    warning_time - now
                ).total_seconds()
                if seconds_to_warning > 0:
                    logger.info(
                        "Current Moscow time: %s",
                        now.strftime(
                            "%H:%M:%S"
                        ),
                    )
                    logger.info(
                        "Warning at: %s",
                        warning_time.strftime(
                            "%H:%M:%S"
                        ),
                    )
                    logger.info(
                        "Signal analysis at: %s",
                        target.strftime(
                            "%H:%M:%S"
                        ),
                    )
                    await asyncio.sleep(
                        seconds_to_warning
                    )
                # --------------------------------------------
                # WARNING
                # --------------------------------------------
                logger.info(
                    "Sending 2-minute warning."
                )
                await send_signal_warning(
                    bot,
                    target,
                )
                # --------------------------------------------
                # Ждём до времени анализа
                # --------------------------------------------
                now = datetime.now(
                    MOSCOW
                )
                seconds_to_signal = (
                    target - now
                ).total_seconds()
                if seconds_to_signal > 0:
                    await asyncio.sleep(
                        seconds_to_signal
                    )
                # --------------------------------------------
                # ANALYSIS
                # --------------------------------------------
                logger.info(
                    "20-minute interval reached."
                )
                await run_signal_cycle(
                    bot=bot,
                    market=market,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Scheduler cycle error."
                )
                await asyncio.sleep(
                    10
                )
    finally:
        checker_task.cancel()
        try:
            await checker_task
        except asyncio.CancelledError:
            pass
        logger.info(
            "Signal scheduler stopped."
        )
