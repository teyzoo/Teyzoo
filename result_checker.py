from __future__ import annotations

import logging
from datetime import datetime

from market import (
    MarketClient,
    MarketDataError,
)
from models import Direction
from signal_results import (
    SignalCheckResult,
    check_signal_result,
)
from signal_tracker import (
    TrackedSignal,
)
from time_utils import MOSCOW


logger = logging.getLogger(
    "result_checker"
)


async def get_close_price(
    market: MarketClient,
    symbol: str,
) -> float:

    candles = await market.get_candles(
        symbol=symbol,
        timeframe="1m",
        limit=5,
    )

    if not candles:

        raise MarketDataError(
            "Не удалось получить свечи "
            "для проверки результата."
        )

    return candles[-1].close


async def check_tracked_signal(
    market: MarketClient,
    signal: TrackedSignal,
) -> SignalCheckResult:

    now = datetime.now(
        MOSCOW
    )

    exit_price = await get_close_price(
        market=market,
        symbol=signal.symbol,
    )

    result = check_signal_result(
        signal_id=signal.signal_id,
        direction=signal.direction,
        entry_price=signal.entry_price,
        exit_price=exit_price,
        checked_at=now,
    )

    logger.info(
        "Signal #%s result: %s",
        signal.signal_id,
        "WIN"
        if result.won
        else "LOSS",
    )

    return result
