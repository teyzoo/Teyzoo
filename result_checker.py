from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from database import (
    get_pending_signals,
)
from market import MarketClient
from signal_result_checker import (
    SignalResultChecker,
)
from signal_result_handler import (
    handle_signal_result,
)


logger = logging.getLogger(
    "result_checker"
)


async def check_results_once(
    bot: Bot,
    market: MarketClient,
) -> int:

    checker = SignalResultChecker(
        market
    )

    pending_before = (
        await get_pending_signals()
    )

    pending_ids = {
        signal.id
        for signal in pending_before
    }

    await checker.check_once()

    pending_after = (
        await get_pending_signals()
    )

    pending_after_ids = {
        signal.id
        for signal in pending_after
    }

    resolved_ids = (
        pending_ids
        - pending_after_ids
    )

    for signal_id in resolved_ids:

        try:

            await handle_signal_result(
                bot,
                signal_id,
            )

        except Exception:

            logger.exception(
                "Could not send result "
                "for signal #%s.",
                signal_id,
            )

    return len(resolved_ids)


async def result_checker_loop(
    bot: Bot,
    market: MarketClient,
    interval: int = 15,
) -> None:

    logger.info(
        "Result checker started."
    )

    while True:

        try:

            await check_results_once(
                bot=bot,
                market=market,
            )

        except asyncio.CancelledError:
            raise

        except Exception:

            logger.exception(
                "Result checker error."
            )

        await asyncio.sleep(
            interval
        )
