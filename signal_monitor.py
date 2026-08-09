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

        direction = parse_direction(
            signal.direction
        )

        if direction is None:
            return False

        if signal.entry_price is None:
            return False

        tracked = TrackedSignal(
            signal_id=signal.id,
            symbol=signal.symbol,
            direction=direction,
            entry_price=signal.entry_price,
            expiry_time=(
                signal.created_at
            ),
        )

        try:

            exit_price = (
                await self.tracker
                .get_current_price(
                    signal.symbol
                )
            )

        except Exception:

            logger.exception(
                "Could not get exit price "
                "for signal #%s.",
                signal_id,
            )

            return False

        won = (
            self.tracker.calculate_result(
                direction=tracked.direction,
                entry_price=tracked.entry_price,
                exit_price=exit_price,
            )
        )

        status = (
            "WON"
            if won
            else "LOST"
        )

        await update_signal_result(
            signal_id=signal.id,
            status=status,
            exit_price=exit_price,
            reason=(
                "Price moved in "
                "signal direction."
                if won
                else
                "Price moved against "
                "signal direction."
            ),
        )

        return True

    async def scan_once(self) -> int:

        signals = (
            await get_pending_signals()
        )

        resolved = 0

        for signal in signals:

            try:

                if signal.entry_price is None:
                    continue

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
        interval: int = 30,
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
