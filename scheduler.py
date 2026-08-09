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


logger = logging.getLogger(
    "scheduler"
)


# ============================================================
# НАСТРОЙКИ
# ============================================================

# Минимальный score для отправки сигнала.
# Слабые сигналы не отправляем.
MIN_SIGNAL_SCORE = 85.0

# Сколько причин максимум показываем пользователю.
MAX_REASONS = 8


# ============================================================
# ОТПРАВКА ПОЛЬЗОВАТЕЛЯМ
# ============================================================

async def send_to_users(
    bot: Bot,
    text: str,
):

    users = await get_active_users()

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
# АНАЛИЗ ОДНОГО ЦИКЛА
# ============================================================

async def run_signal_cycle(
    bot: Bot,
    market: MarketClient,
):

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
    # 1. Создаём selector
    # --------------------------------------------------------

    try:

        selector = PairSelector(
            market=market,
            quality_filter=(
                quality_filter
            ),
        )

    except Exception:

        logger.exception(
            "Could not create PairSelector."
        )

        await send_no_signal(
            bot,
            (
                "⚠️ Не удалось "
                "запустить анализ рынка."
            ),
        )

        return

    # --------------------------------------------------------
    # 2. Ищем лучшую пару
    # --------------------------------------------------------

    try:

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
            (
                "📡 Актуальные данные "
                "рынка недоступны."
            ),
        )

        return

    except asyncio.TimeoutError:

        logger.error(
            "Market request timeout."
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
            "Pair selection failed."
        )

        await send_no_signal(
            bot,
            (
                "⚠️ Анализ рынка "
                "завершился ошибкой."
            ),
        )

        return

    # --------------------------------------------------------
    # 3. Ни одна пара не прошла фильтр
    # --------------------------------------------------------

    if best is None:

        logger.info(
            "No pair passed filters."
        )

        await send_no_signal(
            bot,
            (
                "Ни одна доступная пара "
                "не прошла строгую "
                "фильтрацию."
            ),
        )

        return

    logger.info(
        "Best pair: %s",
        best.symbol,
    )

    # --------------------------------------------------------
    # 4. Получаем результат
    # --------------------------------------------------------

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
    # 5. Проверяем направление
    # --------------------------------------------------------

    if result.direction is None:

        logger.info(
            "No confirmed direction."
        )

        await send_no_signal(
            bot,
            (
                "Нет единого "
                "подтверждённого направления."
            ),
        )

        return

    # --------------------------------------------------------
    # 6. Проверяем score
    # --------------------------------------------------------

    if (
        result.quality_score
        < MIN_SIGNAL_SCORE
    ):

        logger.info(
            "Signal rejected by score: %.2f",
            result.quality_score,
        )

        await send_no_signal(
            bot,
            (
                "Сигнал не прошёл "
                "минимальный Quality Score.\n\n"
                f"🎯 Текущий score: "
                f"<b>"
                f"{result.quality_score:.1f}%"
                f"</b>\n"
                f"🎯 Требуется: "
                f"<b>"
                f"{MIN_SIGNAL_SCORE:.1f}%"
                f"</b>"
            ),
        )

        return

    # --------------------------------------------------------
    # 7. Проверяем Signal Policy
    # --------------------------------------------------------

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
            (
                "Не удалось проверить "
                "надёжность сигнала."
            ),
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
                f"Сигнал отфильтрован.\n\n"
                f"Причина: "
                f"<b>"
                f"{policy.reason}"
                f"</b>"
            ),
        )

        return

    # --------------------------------------------------------
    # 8. Определяем время закрытия
    # --------------------------------------------------------

    close_time = (
        next_20_minute_mark(
            started_at
        )
    )

    logger.info(
        "Signal close time: %s",
        close_time.strftime(
            "%H:%M:%S"
        ),
    )

    # --------------------------------------------------------
    # 9. Направление
    # --------------------------------------------------------

    if result.direction.value == "UP":

        direction_text = (
            "📈 <b>ВВЕРХ</b>"
        )

    elif (
        result.direction.value
        == "DOWN"
    ):

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

    historical_probability = (
        getattr(
            policy,
            "historical_probability",
            None,
        )
    )

    if (
        historical_probability
        is not None
    ):

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
                historical_probability=(
                    historical_probability
                ),
            )
        )

    except TypeError:

        # Совместимость со старой
        # версией database.py,
        # если historical_probability
        # ещё не добавлен.

        logger.warning(
            "save_signal() does not "
            "support historical_probability."
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

    except Exception:

        logger.exception(
            "Could not save signal."
        )

        await send_no_signal(
            bot,
            (
                "Не удалось сохранить "
                "сигнал в базе данных."
            ),
        )

        return

    # --------------------------------------------------------
    # 12. Формируем причины
    # --------------------------------------------------------

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
            "• Подтверждения "
            "не указаны."
        )

    # --------------------------------------------------------
    # 13. Формируем сообщение
    # --------------------------------------------------------

    text = (
        "🚨 <b>TEYZUS SIGNAL</b>\n\n"

        f"💱 Пара: "
        f"<b>{best.symbol}</b>\n\n"

        f"{direction_text}\n\n"

        "⏰ <b>ЗАКРЫТЬ СДЕЛКУ:</b>\n"
        f"<b>"
        f"{format_moscow_time(close_time)}"
        f"</b>\n\n"

        f"🎯 Quality Score: "
        f"<b>"
        f"{result.quality_score:.1f}%"
        f"</b>\n\n"

        f"📊 Историческая вероятность: "
        f"<b>"
        f"{probability_text}"
        f"</b>\n\n"

        f"✅ Подтверждений: "
        f"<b>"
        f"{result.confirmations}/"
        f"{result.total_checks}"
        f"</b>\n\n"

        "🔎 <b>Подтверждения:</b>\n"
        f"{reasons}\n\n"

        f"🆔 Signal #{signal_id}\n\n"

        "⚠️ Сигнал является "
        "аналитическим прогнозом. "
        "Quality Score не означает "
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

    logger.info(
        "Signal scheduler started."
    )

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
                "Current Moscow time: %s",
                now.strftime(
                    "%H:%M:%S"
                ),
            )

            logger.info(
                "Next signal analysis: %s",
                target.strftime(
                    "%H:%M:%S"
                ),
            )

            await asyncio.sleep(
                seconds
            )

            logger.info(
                "20-minute interval reached."
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
