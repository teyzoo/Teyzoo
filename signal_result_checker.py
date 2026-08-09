from __future__ import annotations
import logging
from dataclasses import dataclass
from datetime import datetime
from market import (
    Candle,
    MarketClient,
    MarketDataError,
)
from models import Direction
logger = logging.getLogger(
    "signal_result_checker"
)
@dataclass(slots=True)
class SignalCheck:
    signal_id: int
    symbol: str
    direction: Direction
    entry_price: float
    exit_price: float
    close_time: datetime
    won: bool
    draw: bool
def get_price_at_time(
    candles: list[Candle],
    target_time: datetime,
) -> float | None:
    """
    Находит цену максимально близкую
    к моменту закрытия.
    Берётся первая свеча, которая имеет
    timestamp >= target_time.
    Если такой нет, возвращается None.
    """
    if not candles:
        return None
    candles = sorted(
        candles,
        key=lambda candle: candle.timestamp,
    )
    for candle in candles:
        if candle.timestamp >= target_time:
            return candle.close
    return None
def calculate_result(
    direction: Direction,
    entry_price: float,
    exit_price: float,
) -> tuple[bool, bool]:
    if exit_price == entry_price:
        return False, True
    if direction == Direction.UP:
        return (
            exit_price > entry_price,
            False,
        )
    if direction == Direction.DOWN:
        return (
            exit_price < entry_price,
            False,
        )
    return False, True
class SignalResultChecker:
    def __init__(
        self,
        market: MarketClient,
    ):
        self.market = market
    async def check(
        self,
        signal_id: int,
        symbol: str,
        direction: Direction,
        entry_price: float,
        close_time: datetime,
    ) -> SignalCheck | None:
        try:
            candles = await self.market.get_candles(
                symbol=symbol,
                timeframe="1m",
                limit=20,
            )
        except MarketDataError as exc:
            logger.error(
                "Market error while checking "
                "signal #%s: %s",
                signal_id,
                exc,
            )
            return None
        except Exception:
            logger.exception(
                "Unexpected error while checking "
                "signal #%s.",
                signal_id,
            )
            return None
        exit_price = get_price_at_time(
            candles=candles,
            target_time=close_time,
        )
        if exit_price is None:
            logger.warning(
                "No exit price for signal #%s.",
                signal_id,
            )
            return None
        won, draw = calculate_result(
            direction=direction,
            entry_price=entry_price,
            exit_price=exit_price,
        )
        result = SignalCheck(
            signal_id=signal_id,
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            exit_price=exit_price,
            close_time=close_time,
            won=won,
            draw=draw,
        )
        logger.info(
            "Signal #%s result: %s "
            "(entry=%s exit=%s)",
            signal_id,
            (
                "DRAW"
                if draw
                else "WIN"
                if won
                else "LOSS"
            ),
            entry_price,
            exit_price,
        )
        return result
def format_result(
    result: SignalCheck,
) -> str:
    if result.draw:
        status = "⚪ <b>ВОЗВРАТ</b>"
    elif result.won:
        status = "🟢 <b>WIN</b>"
    else:
        status = "🔴 <b>LOSS</b>"
    if result.direction == Direction.UP:
        direction = "📈 ВВЕРХ"
    else:
        direction = "📉 ВНИЗ"
    return (
        "📊 <b>РЕЗУЛЬТАТ СИГНАЛА</b>\n\n"
        f"💱 Пара: <b>{result.symbol}</b>\n"
        f"{direction}\n\n"
        f"💰 Вход: <b>{result.entry_price}</b>\n"
        f"💰 Закрытие: <b>{result.exit_price}</b>\n\n"
        f"{status}\n\n"
        f"🆔 Signal #{result.signal_id}"
    )
