from __future__ import annotations
import logging
from datetime import timedelta
from aiogram import Bot
from config import (
    SIGNAL_EXPIRY_MINUTES,
)
from database import (
    get_pending_signals,
    save_signal,
)
from market import MarketClient
from pair_selector import PairSelector
from quality_filter import quality_filter
from signal_notifications import (
    send_signal,
)
from signal_policy import (
    signal_policy,
)
from time_utils import (
    format_moscow_time,
    now_moscow,
    next_20_minute_mark,
)
logger = logging.getLogger(
    "signal_generator"
)
class SignalGenerator:
    def __init__(
        self,
        market: MarketClient,
    ):
        self.market = market
        self.selector = PairSelector(
            market=market,
            quality_filter=quality_filter,
        )
    async def has_pending_signal(self) -> bool:
        signals = await get_pending_signals()
        return bool(signals)
    async def generate(
        self,
        bot: Bot,
    ) -> int | None:
        existing = await self.has_pending_signal()
        if existing:
            logger.info(
                "Pending signal already exists. "
                "Skipping generation."
            )
            return None
        logger.info(
            "Starting pair selection..."
        )
        analysis = (
            await self.selector.find_best_pair()
        )
        if analysis is None:
            logger.info(
                "No pair passed Quality Filter."
            )
            return None
        quality = analysis.result
        if quality.direction is None:
            logger.info(
                "Pair rejected: direction is None."
            )
            return None
        policy = signal_policy.evaluate(
            quality_score=quality.quality_score
        )
        if not policy.allowed:
            logger.info(
                "Signal rejected by policy: %s",
                policy.reason,
            )
            return None
        candles = await self.market.get_candles(
            symbol=analysis.symbol,
            timeframe="1m",
            limit=50,
        )
        if not candles:
            logger.info(
                "No candles received for %s.",
                analysis.symbol,
            )
            return None
        entry_price = candles[-1].close
        expiry = next_20_minute_mark()
        minimum_expiry = (
            now_moscow()
            + timedelta(
                minutes=SIGNAL_EXPIRY_MINUTES
            )
        )
        if expiry < minimum_expiry:
            expiry = minimum_expiry
        close_time = format_moscow_time(
            expiry
        )
        signal_id = await save_signal(
            symbol=analysis.symbol,
            direction=quality.direction.value,
            score=quality.quality_score,
            close_time=close_time,
            historical_probability=(
                policy.historical_probability
            ),
            entry_price=entry_price,
        )
        signal = await self._get_signal(
            signal_id
        )
        if signal is not None:
            await send_signal(
                bot,
                signal,
            )
        logger.info(
            "Signal #%s created: %s %s score=%.2f",
            signal_id,
            analysis.symbol,
            quality.direction.value,
            quality.quality_score,
        )
        return signal_id
    @staticmethod
    async def _get_signal(
        signal_id: int,
    ):
        from database import get_signal
        return await get_signal(signal_id)
