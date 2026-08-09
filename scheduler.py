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


logger = logging.getLogger("scheduler")


# ============================================================
# НАСТРОЙКИ
# ============================================================

MIN_SIGNAL_SCORE = 85.0

MAX_REASONS = 8

# За сколько минут предупреждаем пользователя
WARNING_MINUTES = 2

# Интервал дополнительной проверки планировщика
SCHEDULER_CHECK_INTERVAL = 1

# Не отправлять одинаковое предупреждение несколько раз
WARNING_LOCK_SECONDS = 120


# ============================================================
# СОСТОЯНИЕ
# ============================================================

_last_warning_target: datetime | None = None


# ============================================================
# ПОЛЬЗОВАТЕЛИ
# ============================================================

async def send_to_users(
    bot: Bot,
    text: str,
):
    """
    Отправляет сообщение всем активным пользователям.
    """

    try:
        users = await get_active_users()
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

    logger.info(
        "Sending message to %s users.",
        len(users),
    )

    for telegram_id in users:

        try:
            await bot.send_message(
                chat_id=telegram_id,
                text=text,
                parse_mode="HTML",
            )

        except Exception as exc:

            logger.warning(
                "Could not send message to %s: %s",
                telegram_id,
                exc,
            )


# ============================================================
# ПРЕДУПРЕЖДЕНИЕ
# ============================================================

async def send_signal_warning(
    bot: Bot,
    target: datetime,
):
    """
    Предупреждение за 2 минуты до расчётного времени сигнала.
    """

    target_text = format_moscow_time(
        target
    )

    text = (
        "⚠️ <b>ВНИМАНИЕ</b>\n\n"

        "Через <b>2 минуты</b> начнётся "
        "очередной анализ рынка.\n\n"

        f"⏰ Расчётное время: "
        f"<b>{target_text}</b>\n\n"

        "📊 Бот проверит доступные пары "
        "и выдаст сигнал только при "
        "прохождении всех фильтров.\n\n"

        "❗ Это предупреждение "
        "не является сигналом."
    )

    await send_to_users(
        bot,
        text,
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
# АНАЛИЗ ОДНОГО ЦИКЛА
# ============================================================

async def run_signal_cycle(
    bot: Bot,
    market: MarketClient,
):
    """
    Один полный цикл поиска сигнала.
    """

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

    # --------------------------------------------------------
    # 1. Pair selector
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

    # --------------------------------------------------------
    # 4. Логирование
    # --------------------------------------------------------

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
    # 5. Направление
    # --------------------------------------------------------

    if result.direction is None:

        await send_no_signal(
            bot,
            "Нет единого подтверждённого направления.",
        )

        return

    # --------------------------------------------------------
    # 6. Quality score
    # --------------------------------------------------------

    if result.quality_score < MIN_SIGNAL_SCORE:

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
    # 7. Signal Policy
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
            "Signal rejected by policy: %s",
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
    # 8. Время закрытия
    # --------------------------------------------------------

    close_time = next_20_minute_mark(
        started_at
    )

    # --------------------------------------------------------
    # 9. Направление
    # --------------------------------------------------------

    if result.direction.value == "UP":

        direction_text = (
            "📈 <b>ВВЕРХ</b>"
        )

    elif result.direction.value == "DOWN":

        direction_text = (
            "📉 <b>ВНИЗ</b>"
        )

    else:

        logger.error(
            "Unknown direction: %s",
            result.direction,
        )

        await send_no_signal(
            bot,
            "Неизвестное направление сигнала.",
        )

        return

    # --------------------------------------------------------
    # 10. Историческая вероятность
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
    # 11. Сохраняем сигнал
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
            "Old save_signal() detected."
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
    # 12. Причины
    # --------------------------------------------------------

    reasons_list = result.reasons[
        :MAX_REASONS
    ]

    if reasons_list:

        reasons = "\n".join(
            f"• {reason}"
            for reason in reasons_list
        )

    else:

        reasons = (
            "• Подтверждения не указаны."
        )

    # --------------------------------------------------------
    # 13. Сообщение
    # --------------------------------------------------------

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

        "⚠️ Сигнал является аналитическим "
        "прогнозом. Quality Score не означает "
        "гарантированный выигрыш."
    )

    # --------------------------------------------------------
    # 14. Отправляем
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
# ПЛАНИРОВЩИК
# ============================================================

async def signal_scheduler(
    bot: Bot,
    market: MarketClient,
):
    """
    Основной планировщик.

    Например:

    15:18 -> предупреждение
    15:20 -> анализ + сигнал

    15:38 -> предупреждение
    15:40 -> анализ + сигнал

    15:58 -> предупреждение
    16:00 -> анализ + сигнал
    """

    global _last_warning_target

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

            warning_time = (
                target
                - timedelta(
                    minutes=WARNING_MINUTES
                )
            )

            # ------------------------------------------------
            # Предупреждение
            # ------------------------------------------------

            if (
                now >= warning_time
                and now < target
                and _last_warning_target != target
            ):

                logger.info(
                    "Sending 2-minute warning."
                )

                await send_signal_warning(
                    bot=bot,
                    target=target,
                )

                _last_warning_target = target

            # ------------------------------------------------
            # Если время сигнала наступило
            # ------------------------------------------------

            if now >= target:

                logger.info(
                    "Signal time reached: %s",
                    target.strftime(
                        "%H:%M:%S"
                    ),
                )

                await run_signal_cycle(
                    bot=bot,
                    market=market,
                )

                # Сбрасываем состояние.
                _last_warning_target = None

                # Небольшая пауза, чтобы один цикл
                # случайно не запустился дважды.
                await asyncio.sleep(
                    2
                )

            else:

                # Ждём небольшими интервалами,
                # чтобы точно попасть в warning_time.
                seconds_until_warning = (
                    warning_time - now
                ).total_seconds()

                seconds_until_target = (
                    target - now
                ).total_seconds()

                sleep_seconds = min(
                    SCHEDULER_CHECK_INTERVAL,
                    max(
                        0.5,
                        seconds_until_warning
                        if seconds_until_warning > 0
                        else seconds_until_target,
                    ),
                )

                await asyncio.sleep(
                    sleep_seconds
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
