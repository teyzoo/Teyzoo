from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from aiogram import Bot

from database import (
    mark_signal_result,
)

from market import (
    MarketClient,
)

from result_checker import (
    check_tracked_signal,
)

from signal_notifications import (
    send_warning,
)

from signal_result_notifications import (
    send_result,
)

from signal_tracker import (
    signal_tracker,
)

from time_utils import (
    MOSCOW,
)


logger = logging.getLogger(
    "signal_monitor"
)


async def monitor_signals(
    bot: Bot,
    market: MarketClient,
):

    logger.info(
        "Signal monitor started."
    )

    while True:

        try:

            now = datetime.now(
                MOSCOW
            )

            # ============================================
            # ПРЕДУПРЕЖДЕНИЯ
            # ============================================

            warnings = (
                await signal_tracker.get_due_warnings(
                    now
                )
            )

            for signal in warnings:

                try:

                    await send_warning(
                        bot=bot,
                        signal=signal,
                    )

                    await signal_tracker.mark_warning_sent(
                        signal.signal_id
                    )

                    logger.info(
                        "Warning sent for signal #%s",
                        signal.signal_id,
                    )

                except Exception:

                    logger.exception(
                        "Warning failed for #%s",
                        signal.signal_id,
                    )

            # ============================================
            # ПРОВЕРКА ЗАКРЫТЫХ СИГНАЛОВ
            # ============================================

            due_signals = (
                await signal_tracker.get_due_closures(
                    now
                )
            )

            for signal in due_signals:

                try:

                    result = (
                        await check_tracked_signal(
                            market=market,
                            signal=signal,
                        )
                    )

                    await mark_signal_result(
                        signal_id=result.signal_id,
                        won=result.won,
                        entry_price=result.entry_price,
                        exit_price=result.exit_price,
                    )

                    await send_result(
                        bot=bot,
                        result=result,
                    )

                    await signal_tracker.remove(
                        signal.signal_id
                    )

                except Exception:

                    logger.exception(
                        "Could not check "
                        "signal #%s",
                        signal.signal_id,
                    )

            await asyncio.sleep(
                5
            )

        except asyncio.CancelledError:

            logger.info(
                "Signal monitor stopped."
            )

            raise

        except Exception:

            logger.exception(
                "Signal monitor error."
            )

            await asyncio.sleep(
                10
            )
