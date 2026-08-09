from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass
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
# Основной цикл — каждые 20 минут.
SIGNAL_INTERVAL_MINUTES = 20
# Предупреждение отправляется за 2 минуты
# до времени закрытия.
WARNING_MINUTES_BEFORE = 2
# Минимальное качество сигнала.
MIN_SIGNAL_SCORE = 85.0
# Максимальное количество причин
# показываемых пользователю.
MAX_REASONS = 8
# ============================================================
# SIGNAL DATA
# ============================================================
@dataclass(slots=True)
class ScheduledSignal:
    signal_id: int
    symbol: str
    direction: str
    quality_score: float
    confirmations: int
    total_checks: int
    close_time: datetime
    historical_probability: float | None
    reasons: list[str]
# ============================================================
# ОТПРАВКА ПОЛЬЗОВАТЕЛЯМ
# ============================================================
async def send_to_users(
    bot: Bot,
    text: str,
):
    """
    Отправляет сообщение всем активным пользователям.
    Ошибка отправки одному пользователю
    не останавливает рассылку остальным.
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
    """
    Сообщение, когда ни одна пара
    не прошла фильтры.
    """
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
# DIRECTION TEXT
# ============================================================
def get_direction_text(
    direction: str,
) -> str | None:
    if direction == "UP":
        return "📈 <b>ВВЕРХ</b>"
    if direction == "DOWN":
        return "📉 <b>ВНИЗ</b>"
    return None
# ============================================================
# PROBABILITY TEXT
# ============================================================
def format_probability(
    probability: float | None,
) -> str:
    if probability is None:
        return (
            "недостаточно "
            "исторических данных"
        )
    return (
        f"{probability:.1f}%"
    )
# ============================================================
# CREATE SIGNAL
# ============================================================
async def create_signal(
    bot: Bot,
    market: MarketClient,
) -> ScheduledSignal | None:
    """
    Полный анализ рынка.
    Если рынок не даёт достаточно
    подтверждений — возвращается None.
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
    # 1. PairSelector
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
            "⚠️ Не удалось запустить "
            "анализ рынка.",
        )
        return None
    # --------------------------------------------------------
    # 2. Поиск лучшей пары
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
        return None
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
        return None
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
        return None
    # --------------------------------------------------------
    # 3. Нет подходящей пары
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
        return None
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
    # 4. Direction
    # --------------------------------------------------------
    if result.direction is None:
        await send_no_signal(
            bot,
            (
                "Нет единого "
                "подтверждённого направления."
            ),
        )
        return None
    direction = (
        result.direction.value
    )
    direction_text = (
        get_direction_text(
            direction
        )
    )
    if direction_text is None:
        logger.error(
            "Unknown direction: %s",
            direction,
        )
        await send_no_signal(
            bot,
            "Неизвестное направление сигнала.",
        )
        return None
    # --------------------------------------------------------
    # 5. Quality score
    # --------------------------------------------------------
    if (
        result.quality_score
        < MIN_SIGNAL_SCORE
    ):
        logger.info(
            "Rejected by minimum score: %.2f",
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
        return None
    # --------------------------------------------------------
    # 6. Signal Policy
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
                "историческую надёжность сигнала."
            ),
        )
        return None
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
                f"<b>"
                f"{policy.reason}"
                f"</b>"
            ),
        )
        return None
    # --------------------------------------------------------
    # 7. Время закрытия
    # --------------------------------------------------------
    #
    # Например:
    #
    # 11:58 → анализ
    # 12:00 → закрытие
    #
    # В нормальной схеме scheduler запускает
    # создание сигнала заранее.
    #
    close_time = (
        next_20_minute_mark(
            started_at
        )
    )
    logger.info(
        "Close time: %s",
        format_moscow_time(
            close_time
        ),
    )
    # --------------------------------------------------------
    # 8. Историческая вероятность
    # --------------------------------------------------------
    historical_probability = (
        getattr(
            policy,
            "historical_probability",
            None,
        )
    )
    # --------------------------------------------------------
    # 9. Причины
    # --------------------------------------------------------
    reasons = list(
        result.reasons[
            :MAX_REASONS
        ]
    )
    if not reasons:
        reasons = [
            "Дополнительные "
            "подтверждения отсутствуют."
        ]
    # --------------------------------------------------------
    # 10. Сохранение
    # --------------------------------------------------------
    try:
        signal_id = (
            await save_signal(
                symbol=best.symbol,
                direction=direction,
                score=result.quality_score,
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
        #
        # Совместимость со старой
        # database.py.
        #
        logger.warning(
            "save_signal() does not support "
            "historical_probability."
        )
        try:
            signal_id = (
                await save_signal(
                    symbol=best.symbol,
                    direction=direction,
                    score=result.quality_score,
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
            return None
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
        return None
    # --------------------------------------------------------
    # 11. Формируем объект сигнала
    # --------------------------------------------------------
    signal = ScheduledSignal(
        signal_id=signal_id,
        symbol=best.symbol,
        direction=direction,
        quality_score=(
            result.quality_score
        ),
        confirmations=(
            result.confirmations
        ),
        total_checks=(
            result.total_checks
        ),
        close_time=close_time,
        historical_probability=(
            historical_probability
        ),
        reasons=reasons,
    )
    logger.info(
        "Signal #%s created.",
        signal.signal_id,
    )
    return signal
# ============================================================
# WARNING MESSAGE
# ============================================================
def build_warning_message(
    signal: ScheduledSignal,
) -> str:
    """
    Предупреждение за 2 минуты.
    """
    direction_text = (
        get_direction_text(
            signal.direction
        )
        or "❔ НЕИЗВЕСТНО"
    )
    probability_text = (
        format_probability(
            signal.historical_probability
        )
    )
    return (
        "⚠️ <b>ПРЕДУПРЕЖДЕНИЕ</b>\n\n"
        "Через <b>2 минуты</b> "
        "наступает время закрытия "
        "аналитического сигнала.\n\n"
        f"💱 Пара: "
        f"<b>{signal.symbol}</b>\n\n"
        f"{direction_text}\n\n"
        "⏰ <b>ЗАКРЫТЬ СДЕЛКУ:</b>\n"
        f"<b>"
        f"{format_moscow_time(signal.close_time)}"
        f"</b>\n\n"
        f"🎯 Quality Score: "
        f"<b>"
        f"{signal.quality_score:.1f}%"
        f"</b>\n\n"
        f"📊 Историческая вероятность: "
        f"<b>"
        f"{probability_text}"
        f"</b>\n\n"
        f"✅ Подтверждений: "
        f"<b>"
        f"{signal.confirmations}/"
        f"{signal.total_checks}"
        f"</b>\n\n"
        "⚠️ Это аналитический прогноз, "
        "а не гарантия результата."
    )
# ============================================================
# MAIN SIGNAL MESSAGE
# ============================================================
def build_signal_message(
    signal: ScheduledSignal,
) -> str:
    """
    Основное сообщение сигнала.
    """
    direction_text = (
        get_direction_text(
            signal.direction
        )
        or "❔ НЕИЗВЕСТНО"
    )
    probability_text = (
        format_probability(
            signal.historical_probability
        )
    )
    reasons = "\n".join(
        f"• {reason}"
        for reason in signal.reasons
    )
    return (
        "🚨 <b>TEYZUS SIGNAL</b>\n\n"
        f"💱 Пара: "
        f"<b>{signal.symbol}</b>\n\n"
        f"{direction_text}\n\n"
        "⏰ <b>ЗАКРЫТЬ СДЕЛКУ:</b>\n"
        f"<b>"
        f"{format_moscow_time(signal.close_time)}"
        f"</b>\n\n"
        f"🎯 Quality Score: "
        f"<b>"
        f"{signal.quality_score:.1f}%"
        f"</b>\n\n"
        f"📊 Историческая вероятность: "
        f"<b>"
        f"{probability_text}"
        f"</b>\n\n"
        f"✅ Подтверждений: "
        f"<b>"
        f"{signal.confirmations}/"
        f"{signal.total_checks}"
        f"</b>\n\n"
        "🔎 <b>Подтверждения:</b>\n"
        f"{reasons}\n\n"
        f"🆔 Signal #{signal.signal_id}\n\n"
        "⚠️ Сигнал является "
        "аналитическим прогнозом. "
        "Quality Score не означает "
        "гарантированный выигрыш."
    )
# ============================================================
# SEND WARNING
# ============================================================
async def send_signal_warning(
    bot: Bot,
    signal: ScheduledSignal,
):
    """
    Отправляет предупреждение за 2 минуты
    до close_time.
    """
    text = build_warning_message(
        signal
    )
    logger.info(
        "Sending warning for signal #%s.",
        signal.signal_id,
    )
    await send_to_users(
        bot,
        text,
    )
# ============================================================
# SEND MAIN SIGNAL
# ============================================================
async def send_main_signal(
    bot: Bot,
    signal: ScheduledSignal,
):
    """
    Отправляет основное сообщение сигнала.
    """
    text = build_signal_message(
        signal
    )
    logger.info(
        "Sending main signal #%s.",
        signal.signal_id,
    )
    await send_to_users(
        bot,
        text,
    )
# ============================================================
# WAIT UNTIL
# ============================================================
async def wait_until(
    target: datetime,
):
    """
    Точный sleep до указанного времени.
    """
    while True:
        now = datetime.now(
            MOSCOW
        )
        seconds = (
            target - now
        ).total_seconds()
        if seconds <= 0:
            return
        #
        # Не делаем один огромный sleep.
        # Это позволяет корректнее работать
        # после перезапуска/задержек.
        #
        await asyncio.sleep(
            min(
                seconds,
                30.0,
            )
        )
# ============================================================
# SIGNAL LIFECYCLE
# ============================================================
async def run_signal_lifecycle(
    bot: Bot,
    market: MarketClient,
    signal: ScheduledSignal,
):
    """
    Управляет жизненным циклом конкретного сигнала.
    close_time - время закрытия.
    warning_time - за 2 минуты до него.
    """
    close_time = (
        signal.close_time
    )
    warning_time = (
        close_time
        - timedelta(
            minutes=WARNING_MINUTES_BEFORE
        )
    )
    now = datetime.now(
        MOSCOW
    )
    logger.info(
        "Signal #%s lifecycle.",
        signal.signal_id,
    )
    logger.info(
        "Warning time: %s",
        format_moscow_time(
            warning_time
        ),
    )
    logger.info(
        "Close time: %s",
        format_moscow_time(
            close_time
        ),
    )
    # --------------------------------------------------------
    # Если предупреждение ещё впереди
    # --------------------------------------------------------
    if now < warning_time:
        await wait_until(
            warning_time
        )
        await send_signal_warning(
            bot,
            signal,
        )
    # --------------------------------------------------------
    # Если бот был перезапущен уже после
    # warning_time, но до close_time,
    # предупреждение всё равно отправим.
    # --------------------------------------------------------
    elif now < close_time:
        logger.warning(
            "Bot started after warning time "
            "for signal #%s.",
            signal.signal_id,
        )
        await send_signal_warning(
            bot,
            signal,
        )
    # --------------------------------------------------------
    # Ждём время закрытия.
    # --------------------------------------------------------
    await wait_until(
        close_time
    )
    await send_main_signal(
        bot,
        signal,
    )
# ============================================================
# SCHEDULER
# ============================================================
async def signal_scheduler(
    bot: Bot,
    market: MarketClient,
):
    """
    Главный scheduler.
    Каждые 20 минут создаётся новый
    аналитический сигнал.
    Для каждого принятого сигнала:
        T - 2 минуты
              ↓
        WARNING
        T
              ↓
        MAIN SIGNAL
    """
    logger.info(
        "===================================="
    )
    logger.info(
        "Signal scheduler started."
    )
    logger.info(
        "Interval: %s minutes.",
        SIGNAL_INTERVAL_MINUTES,
    )
    logger.info(
        "Warning: %s minutes before close.",
        WARNING_MINUTES_BEFORE,
    )
    logger.info(
        "===================================="
    )
    while True:
        try:
            now = datetime.now(
                MOSCOW
            )
            #
            # Ближайшая отметка 20 минут.
            #
            target = (
                next_20_minute_mark(
                    now
                )
            )
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
            #
            # Ждём ближайший 20-минутный
            # цикл.
            #
            await wait_until(
                target
            )
            logger.info(
                "20-minute mark reached."
            )
            #
            # Создаём сигнал.
            #
            signal = (
                await create_signal(
                    bot=bot,
                    market=market,
                )
            )
            if signal is None:
                logger.info(
                    "No signal created "
                    "for this cycle."
                )
                continue
            #
            # Запускаем lifecycle отдельно.
            #
            #
            # Важно:
            # scheduler не блокируется ожиданием
            # warning/close.
            #
            asyncio.create_task(
                run_signal_lifecycle(
                    bot=bot,
                    market=market,
                    signal=signal,
                )
            )
            logger.info(
                "Signal #%s scheduled.",
                signal.signal_id,
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
