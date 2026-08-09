from __future__ import annotations

import logging

from database import (
    get_pending_signals,
)
from market import MarketClient
from signal_monitor import (
    SignalMonitor,
)


logger = logging.getLogger(
    "signal_result_checker"
)


class SignalResultChecker:

    def __init__(
        self,
        market: MarketClient,
    ):

        self.monitor = SignalMonitor(
            market
        )

    async def check_once(self) -> int:

        resolved = (
            await self.monitor.scan_once()
        )

        logger.info(
            "Resolved signals: %s",
            resolved,
        )

        return resolved

    async def get_pending_count(
        self,
    ) -> int:

        signals = (
            await get_pending_signals()
        )

        return len(signals)
