from __future__ import annotations
import asyncio
import logging
from datetime import datetime
from aiogram import Bot
from database import (
    get_unchecked_signals,
    set_signal_result,
)
from market import (
    MarketClient,
    MarketDataError,
)
from market_factory import (
    create_market_client,
)
from time_utils import (
    MOSCOW,
)
logger = logging.getLogger(
    "signal_result_checker"
)
# ============================================================
# НАСТРОЙКИ
# ============================================================
CHECK_INTERVAL = 10
PRICE_TOLERANCE = 0.0
# ============================================================
# MARKET CLIENT
# ============================================================
market_client: MarketClient | None = None
def get_market_client() -> MarketClient:
    global market_client
    if market_client is None:
        market_client = create_market_client()
    return market_client
# ============================================================
# УВЕДОМЛЕНИЕ
# ============================================================
async def notify_result(
    bot: Bot,
    signal,
    result: str,
    entry_price: float,
    exit_price: float,
):
    """
    Отправляет пользователям результат сигнала.
    Здесь deliberately используется
    список активных пользователей,
    чтобы результат получали
    все подписанные пользователи.
    """
    from database import (
        get_active_users,
    )
    users = await get_active_users()
    if result == "WIN":
        result_text = "✅ <b>WIN</b>"
    else:
        result_text = "❌ <b>LOSS</b>"
    direction = getattr(
        signal,
        "direction",
        "",
    )
    symbol = getattr(
        signal,
        "symbol",
        "",
    )
    signal_id = getattr(
        signal,
        "id",
        0,
    )
    text = (
        "📊 <b>TEYZUS — РЕЗУЛЬТАТ</b>\n\n"
        f"🆔 Signal #{signal_id}\n"
        f"💱 Пара: <b>{symbol}</b>\n\n"
        f"📌 Направление: <b>{direction}</b>\n\n"
        f"💰 Цена входа: "
        f"<b>{entry_price}</b>\n"
        f"💰 Цена закрытия: "
        f"<b>{exit_price}</b>\n\n"
        f"Результат: {result_text}\n\n"
        "⚠️ Результат рассчитан "
        "автоматически по рыночным данным."
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
                "Could not send result "
                "to %s: %s",
                telegram_id,
                exc,
            )
# ============================================================
# ПОЛУЧЕНИЕ ЦЕНЫ
# ============================================================
async def get_current_price(
    market: MarketClient,
    symbol: str,
) -> float:
    """
    Берём последнюю доступную свечу.
    Для проверки результата этого
    достаточно, если API отдаёт
    актуальную последнюю свечу.
    """
    candles = await market.get_candles(
        symbol=symbol,
        timeframe="1m",
        limit=5,
    )
    if not candles:
        raise MarketDataError(
            "No candles available."
        )
    return candles[-1].close
# ============================================================
# ПРОВЕРКА ОДНОГО СИГНАЛА
# ============================================================
async def check_signal(
    bot: Bot,
    signal,
):
    """
    Проверяет один сигнал.
    Сигнал должен уже находиться
    за временем закрытия.
    """
    signal_id = getattr(
        signal,
        "id",
        None,
    )
    symbol = getattr(
        signal,
        "symbol",
        None,
    )
    direction = getattr(
        signal,
        "direction",
        None,
    )
    entry_price = getattr(
        signal,
        "entry_price",
        None,
    )
    if signal_id is None:
        logger.error(
            "Signal without ID."
        )
        return
    if not symbol:
        logger.error(
            "Signal #%s without symbol.",
            signal_id,
        )
        return
    if direction not in (
        "UP",
        "DOWN",
    ):
        logger.error(
            "Signal #%s has invalid direction: %s",
            signal_id,
            direction,
        )
        return
    # --------------------------------------------------------
    # Получаем market
    # --------------------------------------------------------
    market = get_market_client()
    try:
        await market.start()
    except Exception:
        logger.exception(
            "Could not start market client."
        )
        return
    # --------------------------------------------------------
    # Цена входа
    # --------------------------------------------------------
    if entry_price is None:
        logger.error(
            "Signal #%s has no entry price.",
            signal_id,
        )
        return
    # --------------------------------------------------------
    # Цена выхода
    # --------------------------------------------------------
    try:
        exit_price = await get_current_price(
            market,
            symbol,
        )
    except MarketDataError as exc:
        logger.warning(
            "Market data unavailable "
            "for signal #%s: %s",
            signal_id,
            exc,
        )
        return
    except Exception:
        logger.exception(
            "Could not get exit price "
            "for signal #%s.",
            signal_id,
        )
        return
    # --------------------------------------------------------
    # WIN / LOSS
    # --------------------------------------------------------
    if direction == "UP":
        won = (
            exit_price
            > entry_price + PRICE_TOLERANCE
        )
    else:
        won = (
            exit_price
            < entry_price - PRICE_TOLERANCE
        )
    if won:
        result = "WIN"
    else:
        result = "LOSS"
    logger.info(
        "Signal #%s result: %s | "
        "entry=%s exit=%s",
        signal_id,
        result,
        entry_price,
        exit_price,
    )
    # --------------------------------------------------------
    # Сохраняем результат
    # --------------------------------------------------------
    try:
        await set_signal_result(
            signal_id=signal_id,
            result=result,
            exit_price=exit_price,
        )
    except Exception:
        logger.exception(
            "Could not save result "
            "for signal #%s.",
            signal_id,
        )
        return
    # --------------------------------------------------------
    # Уведомляем пользователей
    # --------------------------------------------------------
    await notify_result(
        bot=bot,
        signal=signal,
        result=result,
        entry_price=entry_price,
        exit_price=exit_price,
    )
# ============================================================
# ОСНОВНОЙ CHECKER LOOP
# ============================================================
async def result_checker_loop(
    bot: Bot,
):
    """
    Бесконечный цикл.
    Каждые CHECK_INTERVAL секунд
    проверяет сигналы, у которых
    наступило время закрытия.
    """
    logger.info(
        "Signal result checker started."
    )
    while True:
        try:
            signals = await get_unchecked_signals()
            if signals:
                logger.info(
                    "Found %s signals "
                    "waiting for result.",
                    len(signals),
                )
            for signal in signals:
                try:
                    await check_signal(
                        bot=bot,
                        signal=signal,
                    )
                except Exception:
                    logger.exception(
                        "Failed to check signal."
                    )
            await asyncio.sleep(
                CHECK_INTERVAL
            )
        except asyncio.CancelledError:
            logger.info(
                "Signal result checker stopped."
            )
            raise
        except Exception:
            logger.exception(
                "Result checker error."
            )
            await asyncio.sleep(
                CHECK_INTERVAL
            )
