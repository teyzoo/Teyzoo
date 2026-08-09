from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from aiogram import Bot

from database import (
    get_active_users,
    get_pending_warnings,
    mark_warning_sent,
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

from signal_policy import (
    signal_policy,
)

from signal_notifications import (
    SignalNotifier,
)

from signal_result_handler import (
    check_pending_results,
    parse_close_time,
)

from signal_warning import (
    create_warning,
    format_warning,
    is_warning_time,
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
# НАСТРОЙКИ
# ============================================================

MIN_SIGNAL_SCORE = 85.0

MAX_REASONS = 8

# Как часто проверяем предупреждения
# и результаты.
BACKGROUND_CHECK_INTERVAL = 5


# ============================================================
# ОТПРАВКА ПОЛЬЗОВАТЕЛЯМ
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
            "Could not load active users."
        )

        return

    if not users:

        logger.info(
            "No active users."
        )

        return

    notifier = SignalNotifier(
        bot
    )

    await notifier.send_to_users(
        telegram_ids=users,
        text=text,
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
        bot=bot,
        text=text,
    )


# ============================================================
# ПОЛУЧЕНИЕ ЦЕНЫ ВХОДА
# ============================================================

async def get_entry_price(
    market: MarketClient,
    symbol: str,
) -> float | None:
    """
    Получаем актуальную цену последней
    завершённой/доступной свечи.

    Эта цена сохраняется вместе с сигналом,
    чтобы результат впоследствии считался
    относительно конкретного входа.
    """

    try:

        candles = await market.get_candles(
            symbol=symbol,
            timeframe="1m",
            limit=20,
        )

    except MarketDataError as exc:

        logger.error(
            "Could not get entry price "
            "for %s: %s",
            symbol,
            exc,
        )

        return None

    except Exception:

        logger.exception(
            "Unexpected error getting "
            "entry price for %s.",
            symbol,
        )

        return None

    if not candles:

        return None

    return float(
        candles[-1].close
    )


# ============================================================
# АНАЛИЗ ОДНОГО ЦИКЛА
# ============================================================

async def run_signal_cycle(
    bot: Bot,
    market: MarketClient,
):
    """
    Один полноценный цикл:

        рынок
        ↓
        пары
        ↓
        quality filter
        ↓
        signal policy
        ↓
        entry price
        ↓
        close time
        ↓
        database
        ↓
        users
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
            "⚠️ Не удалось запустить "
            "анализ рынка.",
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
            "📡 Актуальные данные рынка "
            "недоступны.",
        )

        return

    except asyncio.TimeoutError:

        logger.error(
            "Market request timeout."
        )

        await send_no_signal(
            bot,
            "⏱ Получение рыночных данных "
            "превысило таймаут.",
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
    # 3. Ничего не нашли
    # --------------------------------------------------------

    if best is None:

        logger.info(
            "No pair passed filters."
        )

        await send_no_signal(
            bot,
            "Ни одна доступная пара не прошла "
            "строгую фильтрацию.",
        )

        return

    result = best.result

    logger.info(
        "Best pair: %s",
        best.symbol,
    )

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
    # 4. Проверяем направление
    # --------------------------------------------------------

    if result.direction is None:

        await send_no_signal(
            bot,
            "Нет единого подтверждённого "
            "направления.",
        )

        return

    # --------------------------------------------------------
    # 5. Проверяем Quality Score
    # --------------------------------------------------------

    if result.quality_score < MIN_SIGNAL_SCORE:

        await send_no_signal(
            bot,
            (
                "Сигнал не прошёл "
                "минимальный Quality Score.\n\n"

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
            "Не удалось проверить "
            "надёжность сигнала.",
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
    # 7. Получаем entry price
    # --------------------------------------------------------

    entry_price = await get_entry_price(
        market=market,
        symbol=best.symbol,
    )

    if entry_price is None:

        logger.warning(
            "Signal rejected because "
            "entry price unavailable."
        )

        await send_no_signal(
            bot,
            "Не удалось получить актуальную "
            "цену входа.",
        )

        return

    # --------------------------------------------------------
    # 8. Время закрытия
    # --------------------------------------------------------

    close_time = next_20_minute_mark(
        started_at
    )

    logger.info(
        "Signal close time: %s",
        close_time.strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
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

        await send_no_signal(
            bot,
            "Неизвестное направление сигнала.",
        )

        return

    # --------------------------------------------------------
    # 10. Историческая вероятность
    # --------------------------------------------------------

    historical_probability = (
        policy.historical_probability
    )

    if historical_probability is None:

        probability_text = (
            "недостаточно данных"
        )

    else:

        probability_text = (
            f"{historical_probability:.1f}%"
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
            entry_price=entry_price,
        )

    except TypeError:

        # Совместимость со старой БД,
        # если она ещё не принимает новые поля.
        logger.warning(
            "Using legacy save_signal() "
            "signature."
        )

        try:

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
                "Legacy save_signal failed."
            )

            await send_no_signal(
                bot,
                "Не удалось сохранить сигнал "
                "в базе данных.",
            )

            return

    except Exception:

        logger.exception(
            "Could not save signal."
        )

        await send_no_signal(
            bot,
            "Не удалось сохранить сигнал "
            "в базе данных.",
        )

        return

    # --------------------------------------------------------
    # 12. Причины
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
            "• Подтверждения не указаны."
        )

    # --------------------------------------------------------
    # 13. Формируем сигнал
    # --------------------------------------------------------

    text = (
        "🚨 <b>TEYZUS SIGNAL</b>\n\n"

        f"💱 Пара: "
        f"<b>{best.symbol}</b>\n\n"

        f"{direction_text}\n\n"

        "💰 <b>Цена входа:</b>\n"
        f"<b>{entry_price}</b>\n\n"

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
        "прогнозом. Историческая вероятность "
        "не гарантирует результат сделки."
    )

    # --------------------------------------------------------
    # 14. Отправляем сигнал
    # --------------------------------------------------------

    await send_to_users(
        bot=bot,
        text=text,
    )

    logger.info(
        "Signal #%s sent.",
        signal_id,
    )

    logger.info(
        "===================================="
    )


# ============================================================
# ПРОВЕРКА ПРЕДУПРЕЖДЕНИЙ
# ============================================================

async def process_warnings(
    bot: Bot,
):
    """
    Ищет сигналы, которым осталось около 2 минут
    до закрытия, отправляет предупреждение
    и отмечает warning_sent=1.
    """

    try:

        signals = await get_pending_warnings()

    except Exception:

        logger.exception(
            "Could not load pending warnings."
        )

        return

    if not signals:

        return

    now = datetime.now(
        MOSCOW
    )

    for signal in signals:

        try:

            signal_id = int(
                signal["id"]
            )

            close_time = parse_close_time(
                str(signal["close_time"]),
                now=now,
            )

            if close_time is None:
                continue

            warning = create_warning(
                signal_id=signal_id,
                symbol=str(
                    signal["symbol"]
                ),
                direction=str(
                    signal["direction"]
                ),
                close_time=close_time,
            )

            if not is_warning_time(
                warning,
                now,
            ):
                continue

            text = format_warning(
                warning
            )

            users = await get_active_users()

            if users:

                notifier = SignalNotifier(
                    bot
                )

                await notifier.send_warning(
                    telegram_ids=users,
                    text=text,
                )

            # Отмечаем даже при отсутствии
            # пользователей, чтобы scheduler
            # не отправлял предупреждение
            # бесконечно.
            await mark_warning_sent(
                signal_id
            )

            logger.info(
                "Warning sent for signal #%s.",
                signal_id,
            )

        except Exception:

            logger.exception(
                "Warning processing failed."
            )


# ============================================================
# ФОНОВАЯ ПРОВЕРКА
# ============================================================

async def background_signal_monitor(
    bot: Bot,
    market: MarketClient,
):
    """
    Бесконечный монитор.

    Каждые несколько секунд:

        1. Проверяет предупреждения.
        2. Проверяет результаты закрытых сигналов.
    """

    logger.info(
        "Background signal monitor started."
    )

    while True:

        try:

            await process_warnings(
                bot=bot,
            )

            await check_pending_results(
                bot=bot,
                market=market,
            )

            await asyncio.sleep(
                BACKGROUND_CHECK_INTERVAL
            )

        except asyncio.CancelledError:

            logger.info(
                "Background signal monitor stopped."
            )

            raise

        except Exception:

            logger.exception(
                "Background signal monitor error."
            )

            await asyncio.sleep(
                BACKGROUND_CHECK_INTERVAL
            )


# ============================================================
# ОСНОВНОЙ SCHEDULER
# ============================================================

async def signal_scheduler(
    bot: Bot,
    market: MarketClient,
):
    """
    Основной планировщик сигналов.

    Он отвечает только за запуск нового анализа
    каждые 20 минут.

    Предупреждения и результаты работают
    отдельным background monitor.
    """

    logger.info(
        "Signal scheduler started."
    )

    monitor_task = asyncio.create_task(
        background_signal_monitor(
            bot=bot,
            market=market,
        )
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

                seconds = (
                    target - now
                ).total_seconds()

                if seconds < 1:

                    seconds = 1

                logger.info(
                    "Current Moscow time: %s",
                    now.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                )

                logger.info(
                    "Next signal analysis: %s",
                    target.strftime(
                        "%Y-%m-%d %H:%M:%S"
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

                raise

            except Exception:

                logger.exception(
                    "Signal scheduler cycle error."
                )

                await asyncio.sleep(
                    10
                )

    finally:

        monitor_task.cancel()

        try:

            await monitor_task

        except asyncio.CancelledError:

            pass

        logger.info(
            "Signal scheduler fully stopped."
        )
