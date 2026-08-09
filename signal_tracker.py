from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime

from aiogram import Bot

from models import Direction
from signal_results import (
    SignalCheckResult,
    check_signal_result,
)
from time_utils import MOSCOW


logger = logging.getLogger(
    "signal_tracker"
)


@dataclass(slots=True)
class TrackedSignal:
    signal_id: int

    symbol: str

    direction: Direction

    entry_price: float

    close_time: datetime

    warning_sent: bool = False


class SignalTracker:

    def __init__(self):

        self._signals: dict[
            int,
            TrackedSignal,
        ] = {}

        self._lock = asyncio.Lock()

    async def add(
        self,
        signal: TrackedSignal,
    ):

        async with self._lock:

            self._signals[
                signal.signal_id
            ] = signal

            logger.info(
                "Tracking signal #%s",
                signal.signal_id,
            )

    async def remove(
        self,
        signal_id: int,
    ):

        async with self._lock:

            self._signals.pop(
                signal_id,
                None,
            )

    async def get_all(
        self,
    ) -> list[TrackedSignal]:

        async with self._lock:

            return list(
                self._signals.values()
            )

    async def mark_warning_sent(
        self,
        signal_id: int,
    ):

        async with self._lock:

            signal = self._signals.get(
                signal_id
            )

            if signal is not None:
                signal.warning_sent = True

    async def get_due_warnings(
        self,
        now: datetime,
    ) -> list[TrackedSignal]:

        now = now.astimezone(
            MOSCOW
        )

        result = []

        async with self._lock:

            for signal in self._signals.values():

                if signal.warning_sent:
                    continue

                seconds = (
                    signal.close_time
                    - now
                ).total_seconds()

                if (
                    0
                    < seconds
                    <= 120
                ):
                    result.append(
                        signal
                    )

        return result

    async def get_due_closures(
        self,
        now: datetime,
    ) -> list[TrackedSignal]:

        now = now.astimezone(
            MOSCOW
        )

        result = []

        async with self._lock:

            for signal in self._signals.values():

                if (
                    signal.close_time
                    <= now
                ):
                    result.append(
                        signal
                    )

        return result


signal_tracker = SignalTracker()
