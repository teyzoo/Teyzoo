from __future__ import annotations
import logging
from dataclasses import dataclass
from datetime import datetime
from market import (
    MarketClient,
    MarketDataError,
)
from models import (
    Direction,
    SignalStatus,
)
logger = logging.getLogger(
    "signal_result_checker"
)
@dataclass(slots=True)
class SignalCheckResult:
    status: SignalStatus
    entry_price: float
    exit_price: float
    direction: Direction
    checked_at: datetime
    reason: str
class SignalResultChecker:
    def __init__(
        self,
        market: MarketClient,
    ):
        self.market = market
    async def check(
        self,
        symbol: str,
        direction: Direction,
        entry_price: float,
        close_time: datetime,
    ) -> SignalCheckResult:
        candles = await self.market.get_candles(
            symbol=symbol,
            timeframe="1m",
            limit=10,
        )
        if not candles:
            raise MarketDataError(
                "Не удалось получить "
                "свечи для проверки результата."
            )
        suitable = [
            candle
            for candle in candles
            if candle.timestamp >= close_time
        ]
        if suitable:
            exit_candle = suitable[0]
        else:
            exit_candle = candles[-1]
        exit_price = exit_candle.close
        if direction == Direction.UP:
            if exit_price > entry_price:
                status = SignalStatus.WON
                reason = (
                    "Цена закрытия выше "
                    "цены входа."
                )
            elif exit_price < entry_price:
                status = SignalStatus.LOST
                reason = (
                    "Цена закрытия ниже "
                    "цены входа."
                )
            else:
                status = SignalStatus.CANCELLED
                reason = (
                    "Цена не изменилась."
                )
        else:
            if exit_price < entry_price:
                status = SignalStatus.WON
                reason = (
                    "Цена закрытия ниже "
                    "цены входа."
                )
            elif exit_price > entry_price:
                status = SignalStatus.LOST
                reason = (
                    "Цена закрытия выше "
                    "цены входа."
                )
            else:
                status = SignalStatus.CANCELLED
                reason = (
                    "Цена не изменилась."
                )
        return SignalCheckResult(
            status=status,
            entry_price=entry_price,
            exit_price=exit_price,
            direction=direction,
            checked_at=datetime.now(
                close_time.tzinfo
            ),
            reason=reason,
        )
signal_result_checker: (
    SignalResultChecker | None
) = None
def create_signal_result_checker(
    market: MarketClient,
) -> SignalResultChecker:
    global signal_result_checker
    signal_result_checker = (
        SignalResultChecker(market)
    )
    return signal_result_checker
