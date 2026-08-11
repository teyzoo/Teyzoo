from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from database import get_pending_signals
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
    """
    Один проход проверки результатов.
    """

    checker = SignalResultChecker(
        market
    )

    results = await checker.check_once()

    resolved = 0

    for result in results:
        try:
            await handle_signal_result(
                bot=bot,
                signal_id=result.signal_id,
            )
            resolved += 1

        except Exception:
            logger.exception(
                "Could not send result "
                "for signal #%s.",
                result.signal_id,
            )

    return resolved


async def result_checker_loop(
    bot: Bot,
    market: MarketClient,
    interval: int = 15,
    stop_event: asyncio.Event | None = None,
) -> None:
    """
    Постоянный цикл проверки.

    Если stop_event передан, цикл корректно
    завершится через него.
    """

    interval = max(
        5,
        int(interval),
    )

    logger.info(
        "Result checker loop started | interval=%ss",
        interval,
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
                "Result checker cycle failed."
            )

        if stop_event is None:
            await asyncio.sleep(
                interval
            )
            continue

        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=interval,
            )
            break

        except asyncio.TimeoutError:
            continue

    logger.info(
        "Result checker loop stopped."
    )


async def pending_count() -> int:
    """
    Удобный helper для админки/статистики.
    """

    signals = await get_pending_signals()

    return len(signals)


__all__ = [
    "check_results_once",
    "result_checker_loop",
    "pending_count",
]
