from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from database import (
    complete_signal,
    get_signals_ready_for_check,
    set_signal_entry_price,
)

from market import (
    MarketClient,
    MarketDataError,
)

from time_utils import (
    MOSCOW,
)


logger = logging.getLogger(
    "signal_result_checker"
)


class SignalResultChecker:

    """
    Проверяет завершённые сигналы.

    Логика:

        UP:
            exit_price > entry_price
            => WIN

        DOWN:
            exit_price < entry_price
            => WIN

    При равных ценах результат считается ERROR,
    потому что нельзя честно назвать это WIN.
    """

    def __init__(
        self,
        market: MarketClient,
        interval: int = 5,
    ):

        self.market = market

        self.interval = max(
            1,
            interval,
        )

        self.running = False

    # ========================================================
    # CHECK ONE SIGNAL
    # ========================================================

    async def check_signal(
        self,
        signal,
    ) -> bool:

        logger.info(
            "Checking signal #%s: %s %s",
            signal.id,
            signal.symbol,
            signal.direction,
        )

        try:

            candles = (
                await self.market.get_candles(
                    symbol=signal.symbol,
                    timeframe="1m",
                    limit=10,
                )
            )

        except MarketDataError as exc:

            logger.error(
                "Market error for signal #%s: %s",
                signal.id,
                exc,
            )

            return False

        except Exception:

            logger.exception(
                "Could not get market data "
                "for signal #%s.",
                signal.id,
            )

            return False

        if not candles:

            logger.warning(
                "No candles for signal #%s.",
                signal.id,
            )

            return False

        # ----------------------------------------------------
        # Берём последнюю закрытую свечу.
        #
        # В зависимости от API последняя свеча
        # может быть ещё формирующейся.
        #
        # Для нашего универсального клиента
        # используем последнюю доступную свечу.
        # ----------------------------------------------------

        exit_candle = candles[-1]

        exit_price = (
            float(exit_candle.close)
        )

        entry_price = (
            signal.entry_price
        )

        # ----------------------------------------------------
        # Если цена входа не была сохранена,
        # нельзя честно определить результат.
        # ----------------------------------------------------

        if entry_price is None:

            logger.error(
                "Signal #%s has no entry price.",
                signal.id,
            )

            await complete_signal(
                signal_id=signal.id,
                status="ERROR",
                exit_price=exit_price,
                error_message=(
                    "Entry price отсутствует."
                ),
            )

            return True

        entry_price = float(
            entry_price
        )

        # ----------------------------------------------------
        # RESULT
        # ----------------------------------------------------

        direction = (
            str(signal.direction)
            .upper()
        )

        if direction == "UP":

            if exit_price > entry_price:

                status = "WIN"

            elif exit_price < entry_price:

                status = "LOSS"

            else:

                status = "ERROR"

        elif direction == "DOWN":

            if exit_price < entry_price:

                status = "WIN"

            elif exit_price > entry_price:

                status = "LOSS"

            else:

                status = "ERROR"

        else:

            status = "ERROR"

        error_message = None

        if status == "ERROR":

            error_message = (
                "Невозможно определить "
                "результат однозначно."
            )

        await complete_signal(
            signal_id=signal.id,
            status=status,
            exit_price=exit_price,
            error_message=error_message,
        )

        logger.info(
            "Signal #%s => %s | "
            "entry=%.8f exit=%.8f",
            signal.id,
            status,
            entry_price,
            exit_price,
        )

        return True

    # ========================================================
    # CHECK ALL
    # ========================================================

    async def check_pending(
        self,
    ):

        now = datetime.now(
            MOSCOW
        ).replace(
            tzinfo=None
        )

        try:

            signals = (
                await get_signals_ready_for_check(
                    now
                )
            )

        except Exception:

            logger.exception(
                "Could not load signals "
                "ready for checking."
            )

            return

        if not signals:

            return

        logger.info(
            "Found %s signals ready "
            "for result checking.",
            len(signals),
        )

        for signal in signals:

            try:

                await self.check_signal(
                    signal
                )

            except Exception:

                logger.exception(
                    "Unexpected error "
                    "checking signal #%s.",
                    signal.id,
                )

            await asyncio.sleep(
                0.2
            )

    # ========================================================
    # LOOP
    # ========================================================

    async def run(
        self,
    ):

        self.running = True

        logger.info(
            "Signal result checker started."
        )

        while self.running:

            try:

                await self.check_pending()

            except asyncio.CancelledError:

                raise

            except Exception:

                logger.exception(
                    "Result checker error."
                )

            await asyncio.sleep(
                self.interval
            )

    # ========================================================
    # STOP
    # ========================================================

    def stop(self):

        self.running = False


async def signal_result_checker(
    market: MarketClient,
):

    checker = SignalResultChecker(
        market=market,
        interval=5,
    )

    await checker.run()
