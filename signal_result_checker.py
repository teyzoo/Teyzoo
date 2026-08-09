from __future__ import annotations

import logging
from datetime import datetime

from database import (
    get_pending_signals,
    update_signal_result,
)
from market import (
    MarketClient,
    MarketDataError,
)
from models import Direction
from time_utils import (
    MOSCOW,
)

logger = logging.getLogger(
    "signal_results"
)


def parse_close_time(
    value: str,
    reference: datetime,
) -> datetime:

    value = value.replace(
        " МСК",
        "",
    ).strip()

    hour, minute = (
        value.split(":")
    )

    result = reference.replace(
        hour=int(hour),
        minute=int(minute),
        second=0,
        microsecond=0,
    )

    if result < reference:
        result = result.replace(
            day=result.day,
        )

    return result


async def check_pending_signals(
    market: MarketClient,
) -> None:

    signals = await get_pending_signals()

    if not signals:
        return

    now = datetime.now(MOSCOW)

    for signal in signals:

        try:

            close_time = parse_close_time(
                signal["close_time"],
                now,
            )

            if now < close_time:
                continue

            candles = await market.get_candles(
                symbol=signal["symbol"],
                timeframe="1m",
                limit=10,
            )

            if not candles:
                continue

            exit_candle = candles[-1]

            exit_price = exit_candle.close

            entry_price = (
                signal["entry_price"]
            )

            if entry_price is None:
                entry_price = exit_price

            direction = (
                signal["direction"]
            )

            if direction == Direction.UP.value:

                if exit_price > entry_price:
                    result = "WIN"

                elif exit_price < entry_price:
                    result = "LOSS"

                else:
                    result = "DRAW"

            elif direction == Direction.DOWN.value:

                if exit_price < entry_price:
                    result = "WIN"

                elif exit_price > entry_price:
                    result = "LOSS"

                else:
                    result = "DRAW"

            else:
                logger.warning(
                    "Unknown direction for signal %s",
                    signal["id"],
                )
                continue

            await update_signal_result(
                signal_id=int(
                    signal["id"]
                ),
                result=result,
                entry_price=float(
                    entry_price
                ),
                exit_price=float(
                    exit_price
                ),
            )

            logger.info(
                "Signal #%s result: %s",
                signal["id"],
                result,
            )

        except MarketDataError as exc:

            logger.warning(
                "Market error while checking "
                "signal %s: %s",
                signal["id"],
                exc,
            )

        except Exception:

            logger.exception(
                "Failed to check signal %s",
                signal["id"],
            )
