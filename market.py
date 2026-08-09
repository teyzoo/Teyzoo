from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import aiohttp


logger = logging.getLogger("market")


# =========================================================
# ERRORS
# =========================================================

class MarketDataError(Exception):
    """Ошибка получения или обработки рыночных данных."""


# =========================================================
# DATA MODELS
# =========================================================

@dataclass(slots=True)
class Candle:
    timestamp: datetime

    open: float
    high: float
    low: float
    close: float

    volume: float = 0.0


@dataclass(slots=True)
class Quote:
    symbol: str

    bid: float
    ask: float

    timestamp: datetime

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2


# =========================================================
# MARKET PROVIDER
# =========================================================

class MarketProvider:

    async def start(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> list[Candle]:

        raise NotImplementedError


# =========================================================
# HTTP PROVIDER
# =========================================================

class HTTPMarketProvider(
    MarketProvider
):

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout: int = 15,
    ) -> None:

        self.base_url = (
            base_url.rstrip("/")
        )

        self.api_key = api_key

        self.timeout = timeout

        self.session: (
            aiohttp.ClientSession | None
        ) = None

    # -----------------------------------------------------
    # START
    # -----------------------------------------------------

    async def start(self) -> None:

        if self.session is not None:
            return

        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(
                total=self.timeout
            ),
            raise_for_status=False,
        )

        logger.info(
            "HTTP market provider started."
        )

    # -----------------------------------------------------
    # CLOSE
    # -----------------------------------------------------

    async def close(self) -> None:

        if self.session is None:
            return

        await self.session.close()

        self.session = None

        logger.info(
            "HTTP market provider closed."
        )

    # -----------------------------------------------------
    # HEADERS
    # -----------------------------------------------------

    def _build_headers(
        self,
    ) -> dict[str, str]:

        headers: dict[str, str] = {
            "Accept": "application/json",
        }

        if self.api_key:
            headers["Authorization"] = (
                f"Bearer {self.api_key}"
            )

        return headers

    # -----------------------------------------------------
    # GET CANDLES
    # -----------------------------------------------------

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> list[Candle]:

        if self.session is None:

            raise MarketDataError(
                "Market provider is not started."
            )

        params = {
            "symbol": symbol,
            "timeframe": timeframe,
            "limit": limit,
        }

        headers = self._build_headers()

        logger.debug(
            "Request candles: symbol=%s timeframe=%s limit=%s",
            symbol,
            timeframe,
            limit,
        )

        try:

            async with self.session.get(
                self.base_url,
                params=params,
                headers=headers,
            ) as response:

                body = await response.text()

                if response.status != 200:

                    raise MarketDataError(
                        "Market API returned HTTP "
                        f"{response.status}: "
                        f"{body[:500]}"
                    )

                try:

                    data = await response.json(
                        content_type=None
                    )

                except Exception as exc:

                    raise MarketDataError(
                        "Market API returned "
                        "invalid JSON."
                    ) from exc

        except asyncio.TimeoutError as exc:

            raise MarketDataError(
                "Market API timeout."
            ) from exc

        except aiohttp.ClientError as exc:

            raise MarketDataError(
                "Market API connection error: "
                f"{exc}"
            ) from exc

        return self._parse_candles(data)

    # -----------------------------------------------------
    # PARSE CANDLES
    # -----------------------------------------------------

    @staticmethod
    def _parse_candles(
        data: Any,
    ) -> list[Candle]:

        raw: Any = None

        if isinstance(data, dict):

            raw = data.get("candles")

            if raw is None:
                raw = data.get("data")

            if raw is None:
                raw = data.get("results")

        elif isinstance(data, list):

            raw = data

        if not isinstance(raw, list):

            raise MarketDataError(
                "Market response does not contain "
                "a candle list."
            )

        result: list[Candle] = []

        for item in raw:

            if not isinstance(
                item,
                dict,
            ):
                continue

            try:

                timestamp = item.get(
                    "timestamp"
                )

                if timestamp is None:

                    timestamp = item.get(
                        "time"
                    )

                if timestamp is None:

                    timestamp = item.get(
                        "datetime"
                    )

                if timestamp is None:
                    continue

                timestamp = (
                    HTTPMarketProvider._parse_timestamp(
                        timestamp
                    )
                )

                open_price = float(
                    item.get(
                        "open"
                    )
                )

                high_price = float(
                    item.get(
                        "high"
                    )
                )

                low_price = float(
                    item.get(
                        "low"
                    )
                )

                close_price = float(
                    item.get(
                        "close"
                    )
                )

                volume = float(
                    item.get(
                        "volume",
                        0,
                    )
                )

                candle = Candle(
                    timestamp=timestamp,
                    open=open_price,
                    high=high_price,
                    low=low_price,
                    close=close_price,
                    volume=volume,
                )

            except (
                KeyError,
                TypeError,
                ValueError,
            ):

                continue

            # ---------------------------------------------
            # VALIDATION
            # ---------------------------------------------

            if candle.high < candle.low:
                continue

            if candle.open <= 0:
                continue

            if candle.high <= 0:
                continue

            if candle.low <= 0:
                continue

            if candle.close <= 0:
                continue

            if not (
                candle.low
                <= candle.open
                <= candle.high
            ):
                continue

            if not (
                candle.low
                <= candle.close
                <= candle.high
            ):
                continue

            if candle.volume < 0:
                candle.volume = 0.0

            result.append(candle)

        result.sort(
            key=lambda item: item.timestamp
        )

        if len(result) < 20:

            raise MarketDataError(
                "Too few valid candles: "
                f"{len(result)}."
            )

        return result

    # -----------------------------------------------------
    # PARSE TIMESTAMP
    # -----------------------------------------------------

    @staticmethod
    def _parse_timestamp(
        value: Any,
    ) -> datetime:

        if isinstance(
            value,
            datetime,
        ):

            timestamp = value

            if timestamp.tzinfo is None:

                timestamp = timestamp.replace(
                    tzinfo=timezone.utc
                )

            return timestamp.astimezone(
                timezone.utc
            )

        if isinstance(
            value,
            (int, float),
        ):

            numeric = float(value)

            # Unix timestamp в миллисекундах.
            if numeric > 10_000_000_000:

                numeric /= 1000

            return datetime.fromtimestamp(
                numeric,
                tz=timezone.utc,
            )

        text = str(value).strip()

        if not text:

            raise ValueError(
                "Empty timestamp."
            )

        # ISO-8601.
        normalized = text.replace(
            "Z",
            "+00:00",
        )

        try:

            timestamp = datetime.fromisoformat(
                normalized
            )

        except ValueError:

            # Иногда API отдаёт строковый Unix timestamp.
            numeric = float(text)

            if numeric > 10_000_000_000:
                numeric /= 1000

            timestamp = datetime.fromtimestamp(
                numeric,
                tz=timezone.utc,
            )

        if timestamp.tzinfo is None:

            timestamp = timestamp.replace(
                tzinfo=timezone.utc
            )

        return timestamp.astimezone(
            timezone.utc
        )


# =========================================================
# MARKET CLIENT
# =========================================================

class MarketClient:

    def __init__(
        self,
        provider: MarketProvider,
    ) -> None:

        self.provider = provider

    # -----------------------------------------------------
    # START
    # -----------------------------------------------------

    async def start(self) -> None:

        await self.provider.start()

        logger.info(
            "Market client started."
        )

    # -----------------------------------------------------
    # CLOSE
    # -----------------------------------------------------

    async def close(self) -> None:

        await self.provider.close()

        logger.info(
            "Market client closed."
        )

    # -----------------------------------------------------
    # GET CANDLES
    # -----------------------------------------------------

    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "1m",
        limit: int = 200,
    ) -> list[Candle]:

        if not symbol:

            raise ValueError(
                "Symbol is required."
            )

        if not timeframe:

            raise ValueError(
                "Timeframe is required."
            )

        if limit < 20:

            raise ValueError(
                "At least 20 candles are required."
            )

        if limit > 5000:

            raise ValueError(
                "Maximum candle limit is 5000."
            )

        candles = (
            await self.provider.get_candles(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
            )
        )

        if len(candles) < 20:

            raise MarketDataError(
                "Insufficient market candles."
            )

        return candles

    # -----------------------------------------------------
    # MULTI TIMEFRAME
    # -----------------------------------------------------

    async def get_multi_timeframe(
        self,
        symbol: str,
        timeframes: tuple[str, ...],
        limit: int = 200,
    ) -> dict[
        str,
        list[Candle],
    ]:

        if not timeframes:

            raise ValueError(
                "At least one timeframe is required."
            )

        result: dict[
            str,
            list[Candle],
        ] = {}

        for timeframe in timeframes:

            result[timeframe] = (
                await self.get_candles(
                    symbol=symbol,
                    timeframe=timeframe,
                    limit=limit,
                )
            )

        return result

    # -----------------------------------------------------
    # SAFE MULTI TIMEFRAME
    # -----------------------------------------------------

    async def get_available_timeframes(
        self,
        symbol: str,
        timeframes: tuple[str, ...],
        limit: int = 200,
    ) -> dict[
        str,
        list[Candle],
    ]:

        result: dict[
            str,
            list[Candle],
        ] = {}

        for timeframe in timeframes:

            try:

                candles = (
                    await self.get_candles(
                        symbol=symbol,
                        timeframe=timeframe,
                        limit=limit,
                    )
                )

            except (
                MarketDataError,
                ValueError,
            ) as exc:

                logger.warning(
                    "Could not load %s %s: %s",
                    symbol,
                    timeframe,
                    exc,
                )

                continue

            result[timeframe] = candles

        return result


# =========================================================
# EXPORTS
# =========================================================

__all__ = [
    "Candle",
    "Quote",
    "MarketDataError",
    "MarketProvider",
    "HTTPMarketProvider",
    "MarketClient",
]
