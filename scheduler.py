from __future__ import annotations
import asyncio
import logging
from datetime import datetime
from aiogram import Bot
from database import (
    get_active_users,
    get_pending_signals,
    save_signal,
    update_signal_result,
)
from market import (
    MarketClient,
    MarketDataError,
)
from models import (
    Direction,
)
from pair_selector import (
    PairSelector,
)
from probability import (
    probability_calibrator,
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
WARNING_MINUTES = 2
MAX_REASONS = 8
CHECK_INTERVAL_SECONDS = 5
# ============================================================
# SEND TO USERS
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
    direction: Direction,
    close_time: datetime,
    score: float,
) -> None:
    if direction == Direction.UP:
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
        "⏰ <b>ЗАКРЫТИЕ СДЕЛКИ:</b>\n"
        f"<b>"
        f"{format_moscow_time(close_time)}"
        f"</b>\n\n"
        "⏳ До времени закрытия "
        "<b>2 минуты</b>.\n\n"
        f"🎯 Quality Score: "
        f"<b>{score:.1f}%</b>\n\n"
        "⚠️ Это предварительное "
        "уведомление, а не гарантия "
        "результата."
    )
    await send_to_users(
        bot,
        text,
    )
# ============================================================
# SIGNAL CREATION
# ============================================================
async def create_candidate_signal(
    market: MarketClient,
):
    logger.info(
        "Starting signal analysis."
    )
    selector = PairSelector(
        market=market,
        quality_filter=quality_filter,
    )
    best = (
        await selector.find_best_pair()
    )
    if best is None:
        logger.info(
            "No pair passed quality filter."
        )
        return None
    result = best.result
    if result.direction is None:
        logger.info(
            "No confirmed direction."
        )
        return None
    if result.quality_score < MIN_SIGNAL_SCORE:
        logger.info(
            "Rejected by score %.2f",
            result.quality_score,
        )
        return None
    policy = signal_policy.evaluate(
        result.quality_score
    )
    if not policy.allowed:
        logger.info(
            "Rejected by policy: %s",
            policy.reason,
        )
        return None
    close_time = (
        next_20_minute_mark()
    )
    return {
        "symbol": best.symbol,
        "direction": result.direction,
        "quality_score": (
            result.quality_score
        ),
        "confirmations": (
            result.confirmations
        ),
        "total_checks": (
            result.total_checks
        ),
        "historical_probability": (
            policy.historical_probability
        ),
        "close_time": close_time,
        "reasons": (
            result.reasons[:MAX_REASONS]
        ),
    }
# ============================================================
# SEND FINAL SIGNAL
# ============================================================
async def send_final_signal(
    bot: Bot,
    candidate: dict,
    signal_id: int,
) -> None:
    direction = candidate[
        "direction"
    ]
    if direction == Direction.UP:
        direction_text = (
            "📈 <b>ВВЕРХ</b>"
        )
    else:
        direction_text = (
            "📉 <b>ВНИЗ</b>"
        )
    probability = candidate[
        "historical_probability"
    ]
    if probability is None:
        probability_text = (
            "нет достаточной истории"
        )
    else:
        probability_text = (
            f"{probability:.1f}%"
        )
    reasons = candidate[
        "reasons"
    ]
    if reasons:
        reasons_text = "\n".join(
            f"• {reason}"
            for reason in reasons
        )
    else:
        reasons_text = (
            "• Нет дополнительных причин."
        )
    text = (
        "🚨 <b>TEYZUS SIGNAL</b>\n\n"
        f"💱 Пара: "
        f"<b>{candidate['symbol']}</b>\n\n"
        f"{direction_text}\n\n"
        "⏰ <b>ЗАКРЫТЬ СДЕЛКУ:</b>\n"
        f"<b>"
        f"{format_moscow_time(candidate['close_time'])}"
        f"</b>\n\n"
        f"🎯 Quality Score: "
        f"<b>"
        f"{candidate['quality_score']:.1f}%"
        f"</b>\n\n"
        f"📊 Исторический результат "
        f"этого диапазона: "
        f"<b>{probability_text}</b>\n\n"
        f"✅ Подтверждений: "
        f"<b>"
        f"{candidate['confirmations']}/"
        f"{candidate['total_checks']}"
        f"</b>\n\n"
        "🔎 <b>Подтверждения:</b>\n"
        f"{reasons_text}\n\n"
        f"🆔 Signal #{signal_id}\n\n"
        "⚠️ Аналитический прогноз. "
        "Гарантировать выигрыш невозможно."
    )
    await send_to_users(
        bot,
        text,
    )
# ============================================================
# RESULT CHECKER
# ============================================================
async def check_finished_signals(
    bot: Bot,
    market: MarketClient,
) -> None:
    now = datetime.now(
        MOSCOW
    )
    pending = (
        await get_pending_signals()
    )
    if not pending:
        return
    checker = SignalResultChecker(
        market
    )
    for signal in pending:
        close_time = (
            signal.close_time
        )
        if close_time.tzinfo is None:
            close_time = close_time.replace(
                tzinfo=MOSCOW
            )
        else:
            close_time = (
                close_time.astimezone(
                    MOSCOW
                )
            )
        if close_time > now:
            continue
        if signal.entry_price is None:
            logger.warning(
                "Signal #%s has no "
                "entry price.",
                signal.id,
            )
            continue
        try:
            direction = Direction(
                signal.direction
            )
            result = await checker.check(
                symbol=signal.symbol,
                direction=direction,
                entry_price=(
                    signal.entry_price
                ),
                close_time=close_time,
            )
        except Exception:
            logger.exception(
                "Could not check "
                "signal #%s.",
                signal.id,
            )
            continue
        updated = (
            await update_signal_result(
                signal_id=signal.id,
                status=result.status.value,
                entry_price=(
                    result.entry_price
                ),
                exit_price=(
                    result.exit_price
                ),
                checked_at=(
                    result.checked_at
                ),
                reason=result.reason,
            )
        )
        if not updated:
            continue
        if result.status.value == "WON":
            probability_calibrator.add_result(
                score=signal.quality_score,
                won=True,
            )
        elif result.status.value == "LOST":
            probability_calibrator.add_result(
                score=signal.quality_score,
                won=False,
            )
        logger.info(
            "Signal #%s finished: %s",
            signal.id,
            result.status.value,
        )
# ============================================================
# MAIN SIGNAL CYCLE
# ============================================================
async def run_signal_cycle(
    bot: Bot,
    market: MarketClient,
) -> None:
    started_at = datetime.now(
        MOSCOW
    )
    logger.info(
        "Starting cycle at %s",
        started_at.strftime(
            "%H:%M:%S"
        ),
    )
    try:
        candidate = (
            await create_candidate_signal(
                market
            )
        )
    except MarketDataError as exc:
        logger.error(
            "Market data error: %s",
            exc,
        )
        await send_no_signal(
            bot,
            (
                "📡 Актуальные рыночные "
                "данные недоступны."
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
            "Signal analysis failed."
        )
        await send_no_signal(
            bot,
            (
                "⚠️ Во время анализа "
                "произошла ошибка."
            ),
        )
        return
    if candidate is None:
        await send_no_signal(
            bot,
            (
                "Ни одна пара не прошла "
                "строгую фильтрацию."
            ),
        )
        return
    # --------------------------------------------------------
    # ENTRY PRICE
    # --------------------------------------------------------
    try:
        candles = (
            await market.get_candles(
                symbol=candidate["symbol"],
                timeframe="1m",
                limit=5,
            )
        )
        if not candles:
            raise MarketDataError(
                "Нет актуальных свечей."
            )
        entry_price = (
            candles[-1].close
        )
    except Exception:
        logger.exception(
            "Could not obtain entry price."
        )
        await send_no_signal(
            bot,
            (
                "Не удалось получить "
                "актуальную цену."
            ),
        )
        return
    candidate[
        "entry_price"
    ] = entry_price
    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------
    try:
        signal_id = await save_signal(
            symbol=candidate["symbol"],
            direction=(
                candidate["direction"].value
            ),
            score=(
                candidate["quality_score"]
            ),
            close_time=(
                candidate["close_time"]
            ),
            historical_probability=(
                candidate[
                    "historical_probability"
                ]
            ),
            entry_price=entry_price,
            confirmations=(
                candidate[
                    "confirmations"
                ]
            ),
            total_checks=(
                candidate[
                    "total_checks"
                ]
            ),
        )
    except Exception:
        logger.exception(
            "Could not save signal."
        )
        await send_no_signal(
            bot,
            (
                "Не удалось сохранить "
                "сигнал."
            ),
        )
        return
    # --------------------------------------------------------
    # WARNING 2 MINUTES BEFORE CLOSE
    # --------------------------------------------------------
    warning_time = (
        candidate["close_time"]
        .timestamp()
        - WARNING_MINUTES * 60
    )
    now_timestamp = (
        datetime.now(
            MOSCOW
        ).timestamp()
    )
    wait_seconds = (
        warning_time
        - now_timestamp
    )
    if wait_seconds > 0:
        logger.info(
            "Waiting %.1f seconds "
            "before warning.",
            wait_seconds,
        )
        await asyncio.sleep(
            wait_seconds
        )
    await send_signal_warning(
        bot=bot,
        symbol=candidate["symbol"],
        direction=candidate["direction"],
        close_time=candidate["close_time"],
        score=candidate["quality_score"],
    )
    # --------------------------------------------------------
    # FINAL SIGNAL
    # --------------------------------------------------------
    await send_final_signal(
        bot=bot,
        candidate=candidate,
        signal_id=signal_id,
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
            # Сначала проверяем старые
            # сигналы, которые уже должны
            # быть закрыты.
            await check_finished_signals(
                bot=bot,
                market=market,
            )
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
                "Next cycle: %s",
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
                CHECK_INTERVAL_SECONDS
            )
