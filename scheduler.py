from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from market import MarketClient
from result_checker import (
    result_checker_loop,
)
from signal_warning.scheduler import (
    warning_scheduler,
)


logger = logging.getLogger(
    "scheduler"
)


class Scheduler:

    def __init__(
        self,
        bot: Bot,
        market: MarketClient,
    ):

        self.bot = bot
        self.market = market

        self.tasks: list[
            asyncio.Task
        ] = []

    async def start(self) -> None:

        if self.tasks:

            logger.warning(
                "Scheduler already started."
            )

            return

        logger.info(
            "Starting scheduler..."
        )

        self.tasks = [
            asyncio.create_task(
                warning_scheduler(
                    self.bot
                ),
                name="signal_warning",
            ),
            asyncio.create_task(
                result_checker_loop(
                    self.bot,
                    self.market,
                ),
                name="signal_result_checker",
            ),
        ]

        logger.info(
            "Scheduler started: %s tasks.",
            len(self.tasks),
        )

    async def stop(self) -> None:

        if not self.tasks:
            return

        logger.info(
            "Stopping scheduler..."
        )

        for task in self.tasks:

            task.cancel()

        results = await asyncio.gather(
            *self.tasks,
            return_exceptions=True,
        )

        for result in results:

            if isinstance(
                result,
                Exception,
            ):

                logger.debug(
                    "Scheduler task stopped: %s",
                    result,
                )

        self.tasks.clear()

        logger.info(
            "Scheduler stopped."
        )
