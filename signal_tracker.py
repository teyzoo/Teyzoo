from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from market import MarketClient
from models import Direction
from time_utils import ensure_moscow


logger = logging.getLogger("signal_tracker")


@dataclass(slots=True)
class TrackedSignal:
    signal_id: int
    symbol: str
    direction: Direction
    entry_price: float
    expiry_time: datetime


class SignalTracker:

    def __init__(
        self,
        market: MarketClient,
    ):
        self.market = market

    async def get_current_price(
        self,
        symbol: str,
    ) -> float:

        candles = await self.market.get_candles(
            symbol=symbol,
            timeframe="1m",
            limit=20,
        )

        if not candles:
            raise RuntimeError(
                "No market candles."
            )

        return float(candles[-1].close)

    @staticmethod
    def calculate_result(
        direction: Direction,
        entry_price: float,
        exit_price: float,
    ) -> bool:

        if direction == Direction.UP:
            return exit_price > entry_price

        if direction == Direction.DOWN:
            return exit_price < entry_price

        return False

    @staticmethod
    def is_expired(
        expiry_time: datetime,
        now: datetime | None = None,
    ) -> bool:

        if now is None:
            from time_utils import now_moscow

            now = now_moscow()

        return ensure_moscow(now) >= ensure_moscow(
            expiry_time
        )

    async def check_signal(
        self,
        signal: TrackedSignal,
    ) -> tuple[bool, float]:

        exit_price = await self.get_current_price(
            signal.symbol
        )

        won = self.calculate_result(
            direction=signal.direction,
            entry_price=signal.entry_price,
            exit_price=exit_price,
        )

        logger.info(
            "Signal #%s result: %s | entry=%s exit=%s",
            signal.signal_id,
            "WON" if won else "LOST",
            signal.entry_price,
            exit_price,
        )

        return won, exit_price
