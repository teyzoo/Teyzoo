from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from database import (
    get_pending_signals,
)
from signal_notifications import (
    send_signal_warning,
)
from time_utils import (
    now_moscow,
    parse_moscow_time,
    signal_warning_time,
)


logger = logging.getLogger(
    "signal_warning"
)


async def warning_scheduler(
    bot: Bot,
    interval: int = 10,
) -> None:

    logger.info(
        "Signal warning scheduler started."
    )

    sent: set[int] = set()

    while True:

        try:

            now = now_moscow()

            signals = (
                await get_pending_signals()
            )

            for signal in signals:

                if signal.id in sent:
                    continue

                try:

                    close_time = (
                        parse_moscow_time(
                            signal.close_time,
                            reference=signal.created_at,
                        )
                    )

                    warning_time = (
                        signal_warning_time(
                            close_time,
                            2,
                        )
                    )

                    if (
                        warning_time
                        <= now
                        < close_time
                    ):

                        await send_signal_warning(
                            bot,
                            signal,
                        )

                        sent.add(
                            signal.id
                        )

                except Exception:

                    logger.exception(
                        "Warning error "
                        "for signal #%s.",
                        signal.id,
                    )

            if len(sent) > 10000:
                sent.clear()

        except asyncio.CancelledError:
            raise

        except Exception:

            logger.exception(
                "Warning scheduler error."
            )

        await asyncio.sleep(
            interval
        )
