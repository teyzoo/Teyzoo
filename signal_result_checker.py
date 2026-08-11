from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from database import (
    get_pending_signals,
    update_signal_result,
)
from market import (
    Candle,
    MarketClient,
    MarketDataError,
    MarketRateLimitError,
)
from models import Direction


logger = logging.getLogger(
    "signal_result_checker"
)


@dataclass(slots=True)
class ResultCheck:
    signal_id: int
    status: str
    exit_price: float | None
    reason: str


class SignalResultChecker:
    """
    Проверяет завершившиеся PENDING-сигналы.

    Для результата используется последняя закрытая
    свеча 1m.

    UP:
        exit > entry -> WON
        exit < entry -> LOST
        equal -> DRAW

    DOWN:
        exit < entry -> WON
        exit > entry -> LOST
        equal -> DRAW
    """

    def __init__(
        self,
        market: MarketClient,
        timeframe: str = "1m",
        candle_limit: int = 50,
    ) -> None:
        self.market = market
        self.timeframe = timeframe
        self.candle_limit = max(
            20,
            int(candle_limit),
        )

    @staticmethod
    def _ensure_utc(
        value: datetime,
    ) -> datetime:
        if value.tzinfo is None:
            return value.replace(
                tzinfo=timezone.utc
            )

        return value.astimezone(
            timezone.utc
        )

    @staticmethod
    def _parse_expiry(
        value: str,
    ) -> datetime | None:
        """
        Поддерживает ISO timestamp.

        Старые версии проекта могут хранить
        close_time как строку вида HH:MM.
        Для такой строки точный день восстановить
        невозможно, поэтому она не используется
        как абсолютное время.
        """

        if not value:
            return None

        text = str(value).strip()

        try:
            parsed = datetime.fromisoformat(
                text.replace(
                    "Z",
                    "+00:00",
                )
            )
        except ValueError:
            return None

        return SignalResultChecker._ensure_utc(
            parsed
        )

    async def _get_last_candle(
        self,
        symbol: str,
    ) -> Candle:
        candles = await self.market.get_candles(
            symbol=symbol,
            timeframe=self.timeframe,
            limit=self.candle_limit,
        )

        if not candles:
            raise MarketDataError(
                f"No candles for {symbol}."
            )

        return candles[-1]

    @staticmethod
    def _calculate_status(
        direction: str,
        entry_price: float,
        exit_price: float,
    ) -> tuple[str, str]:
        normalized = str(
            direction
        ).upper()

        if exit_price == entry_price:
            return (
                "DRAW",
                "Цена закрытия равна цене входа.",
            )

        if normalized == Direction.UP.value:
            if exit_price > entry_price:
                return (
                    "WON",
                    "Цена после сигнала выросла.",
                )

            return (
                "LOST",
                "Цена после сигнала снизилась.",
            )

        if normalized == Direction.DOWN.value:
            if exit_price < entry_price:
                return (
                    "WON",
                    "Цена после сигнала снизилась.",
                )

            return (
                "LOST",
                "Цена после сигнала выросла.",
            )

        return (
            "CANCELLED",
            f"Неизвестное направление: {direction}.",
        )

    async def check_signal(
        self,
        signal,
    ) -> ResultCheck | None:
        if signal.status != "PENDING":
            return None

        if signal.entry_price is None:
            await update_signal_result(
                signal_id=signal.id,
                status="CANCELLED",
                exit_price=None,
                reason=(
                    "У сигнала отсутствует "
                    "entry_price."
                ),
            )

            return ResultCheck(
                signal_id=signal.id,
                status="CANCELLED",
                exit_price=None,
                reason=(
                    "У сигнала отсутствует "
                    "entry_price."
                ),
            )

        expiry = self._parse_expiry(
            signal.close_time
        )

        now = datetime.now(
            timezone.utc
        )

        # Если close_time невозможно распарсить,
        # не закрываем сигнал мгновенно.
        if expiry is not None and now < expiry:
            return None

        candle = await self._get_last_candle(
            signal.symbol
        )

        exit_price = float(
            candle.close
        )

        status, reason = (
            self._calculate_status(
                direction=signal.direction,
                entry_price=float(
                    signal.entry_price
                ),
                exit_price=exit_price,
            )
        )

        updated = await update_signal_result(
            signal_id=signal.id,
            status=status,
            exit_price=exit_price,
            reason=reason,
        )

        if not updated:
            logger.warning(
                "Signal #%s disappeared "
                "during result update.",
                signal.id,
            )
            return None

        return ResultCheck(
            signal_id=signal.id,
            status=status,
            exit_price=exit_price,
            reason=reason,
        )

    async def check_once(
        self,
    ) -> list[ResultCheck]:
        pending = await get_pending_signals()

        if not pending:
            return []

        results: list[ResultCheck] = []

        for signal in pending:
            try:
                result = await self.check_signal(
                    signal
                )

                if result is not None:
                    results.append(result)

            except MarketRateLimitError:
                logger.warning(
                    "Market rate limit while "
                    "checking signal #%s.",
                    signal.id,
                )
                break

            except MarketDataError as exc:
                logger.warning(
                    "Market error for signal #%s: %s",
                    signal.id,
                    exc,
                )

            except Exception:
                logger.exception(
                    "Failed to check signal #%s.",
                    signal.id,
                )

        return results


__all__ = [
    "ResultCheck",
    "SignalResultChecker",
]
