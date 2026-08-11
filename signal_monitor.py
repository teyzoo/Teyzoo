from __future__ import annotations
import asyncio
import logging
from database import (
    get_pending_signals,
    get_signal,
    update_signal_result,
)
from market import MarketClient
from models import Direction
from signal_tracker import (
    SignalTracker,
    TrackedSignal,
)
from time_utils import (
    now_moscow,
    parse_moscow_time,
)
logger = logging.getLogger(
    "signal_monitor"
)
def parse_direction(
    value: str,
) -> Direction | None:
    try:
        return Direction(value)
    except ValueError:
        return None
class SignalMonitor:
    def __init__(
        self,
        market: MarketClient,
    ):
        self.tracker = SignalTracker(
            market
        )
    async def resolve_signal(
        self,
        signal_id: int,
    ) -> bool:
        signal = await get_signal(
            signal_id
        )
        if signal is None:
            return False
        if signal.status != "PENDING":
            return False
        if signal.entry_price is None:
            return False
        direction = parse_direction(
            signal.direction
        )
        if direction is None:
            logger.error(
                "Unknown direction for signal #%s: %s",
                signal_id,
                signal.direction,
            )
            return False
        now = now_moscow()
        try:
            close_time = parse_moscow_time(
                signal.close_time,
                reference=signal.created_at,
            )
        except Exception:
            logger.exception(
                "Invalid close_time for signal #%s: %s",
                signal_id,
                signal.close_time,
            )
            return False
        close_time = close_time.astimezone(
            now.tzinfo
        )
        if now < close_time:
            return False
        tracked = TrackedSignal(
            signal_id=signal.id,
            symbol=signal.symbol,
            direction=direction,
            entry_price=float(
                signal.entry_price
            ),
            expiry_time=close_time,
        )
        try:
            won, exit_price = (
                await self.tracker.check_signal(
                    tracked
                )
            )
        except Exception:
            logger.exception(
                "Could not get exit price "
                "for signal #%s.",
                signal_id,
            )
            return False
        status = (
            "WON"
            if won
            else "LOST"
        )
        reason = (
            "Цена закрытия выше "
            "цены входа для UP."
            if (
                won
                and direction == Direction.UP
            )
            else
            "Цена закрытия ниже "
            "цены входа для DOWN."
            if (
                won
                and direction == Direction.DOWN
            )
            else
            "Цена закрытия не подтвердила "
            "направление сигнала."
        )
        updated = await update_signal_result(
            signal_id=signal.id,
            status=status,
            exit_price=exit_price,
            reason=reason,
        )
        return updated
    async def scan_once(
        self,
    ) -> int:
        signals = (
            await get_pending_signals()
        )
        resolved = 0
        for signal in signals:
            try:
                if await self.resolve_signal(
                    signal.id
                ):
                    resolved += 1
            except Exception:
                logger.exception(
                    "Failed resolving "
                    "signal #%s.",
                    signal.id,
                )
        return resolved
    async def run(
        self,
        interval: int = 15,
    ) -> None:
        logger.info(
            "Signal monitor started."
        )
        while True:
            try:
                await self.scan_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Signal monitor error."
                )
            await asyncio.sleep(
                interval
            )
