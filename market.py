from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import aiohttp


logger = logging.getLogger(
    "market"
)


class MarketDataError(Exception):
    pass


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
        return (
            self.bid + self.ask
        ) / 2


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


class HTTPMarketProvider(
    MarketProvider
):

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout: int = 15,
    ):

        self.base_url = (
            base_url.rstrip("/")
        )

        self.api_key = api_key

        self.timeout = timeout

        self.session: (
            aiohttp.ClientSession | None
        ) = None

    async def start(self) -> None:

        if self.session is not None:
            return

        self.session = (
            aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(
                    total=self.timeout
                )
            )
        )

    async def close(self) -> None:

        if self.session is None:
            return

        await self.session.close()

        self.session = None

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

        headers: dict[str, str] = {}

        if self.api_key:
            headers["Authorization"] = (
                f"Bearer {self.api_key}"
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
                    data = await response.json()
                except Exception as exc:
                    raise MarketDataError(
                        "Market API returned "
                        "invalid JSON."
                    ) from exc

        except asyncio_timeout_error() as exc:

            raise MarketDataError(
                "Market API timeout."
            ) from exc

        except aiohttp.ClientError as exc:

            raise MarketDataError(
                "Market API connection error."
            ) from exc

        return self._parse_candles(data)

    @staticmethod
    def _parse_candles(
        data: Any,
    ) -> list[Candle]:

        if isinstance(data, dict):
            raw = data.get("candles")

            if raw is None:
                raw = data.get("data")

        elif isinstance(data, list):
            raw = data

        else:
            raw = None

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

                timestamp = (
                    item["timestamp"]
                )

                if isinstance(
                    timestamp,
                    (int, float),
                ):

                    timestamp = (
                        datetime.fromtimestamp(
                            timestamp,
                            tz=timezone.utc,
                        )
                    )

                else:

                    timestamp = (
                        datetime.fromisoformat(
                            str(timestamp)
                            .replace(
                                "Z",
                                "+00:00",
                            )
                        )
                    )

                candle = Candle(
                    timestamp=timestamp,
                    open=float(
                        item["open"]
                    ),
                    high=float(
                        item["high"]
                    ),
                    low=float(
                        item["low"]
                    ),
                    close=float(
                        item["close"]
                    ),
                    volume=float(
                        item.get(
                            "volume",
                            0,
                        )
                    ),
                )

            except (
                KeyError,
                TypeError,
                ValueError,
            ):
                continue

            if candle.high < candle.low:
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

            if candle.close <= 0:
                continue

            result.append(candle)

        result.sort(
            key=lambda item:
                item.timestamp
        )

        if len(result) < 20:
            raise MarketDataError(
                "Too few valid candles."
            )

        return result


def asyncio_timeout_error():
    import asyncio

    return asyncio.TimeoutError


class MarketClient:

    def __init__(
        self,
        provider: MarketProvider,
    ):

        self.provider = provider

    async def start(self) -> None:
        await self.provider.start()

    async def close(self) -> None:
        await self.provider.close()

    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "1m",
        limit: int = 200,
    ) -> list[Candle]:

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

    async def get_multi_timeframe(
        self,
        symbol: str,
        timeframes: tuple[str, ...],
        limit: int = 200,
    ) -> dict[str, list[Candle]]:

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
