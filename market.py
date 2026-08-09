from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import aiohttp


logger = logging.getLogger("market")


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
    """
    Интерфейс источника рынка.

    Конкретный API подключается
    отдельным классом.
    """

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
    """
    Универсальный HTTP provider.

    Формат ожидаемого ответа:

    {
        "candles": [
            {
                "timestamp": 1234567890,
                "open": 1.1,
                "high": 1.2,
                "low": 1.0,
                "close": 1.15,
                "volume": 123
            }
        ]
    }

    Конкретный URL задаётся через
    MARKET_API_URL.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
    ):

        self.base_url = (
            base_url.rstrip("/")
        )

        self.api_key = api_key

        self.session: (
            aiohttp.ClientSession | None
        ) = None

    async def start(self):

        if self.session:
            return

        self.session = (
            aiohttp.ClientSession(
                timeout=(
                    aiohttp.ClientTimeout(
                        total=15
                    )
                )
            )
        )

    async def close(self):

        if self.session:

            await self.session.close()

            self.session = None

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> list[Candle]:

        if not self.session:

            raise MarketDataError(
                "Market provider не запущен."
            )

        params = {
            "symbol": symbol,
            "timeframe": timeframe,
            "limit": limit,
        }

        headers = {}

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

                if response.status != 200:

                    text = (
                        await response.text()
                    )

                    raise MarketDataError(
                        "Market API HTTP "
                        f"{response.status}: "
                        f"{text[:300]}"
                    )

                data = (
                    await response.json()
                )

        except aiohttp.ClientError as exc:

            raise MarketDataError(
                "Ошибка подключения "
                "к market API."
            ) from exc

        except TimeoutError as exc:

            raise MarketDataError(
                "Market API timeout."
            ) from exc

        return self._parse_candles(
            data
        )

    @staticmethod
    def _parse_candles(
        data,
    ) -> list[Candle]:

        if isinstance(data, dict):

            raw_candles = data.get(
                "candles"
            )

        elif isinstance(data, list):

            raw_candles = data

        else:

            raw_candles = None

        if not isinstance(
            raw_candles,
            list,
        ):

            raise MarketDataError(
                "Не найден массив candles."
            )

        candles: list[Candle] = []

        for item in raw_candles:

            try:

                timestamp = item[
                    "timestamp"
                ]

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

                candles.append(
                    candle
                )

            except (
                KeyError,
                TypeError,
                ValueError,
            ):

                continue

        candles.sort(
            key=lambda candle:
                candle.timestamp
        )

        if len(candles) < 20:

            raise MarketDataError(
                "Получено слишком мало "
                "корректных свечей."
            )

        return candles


class MarketClient:

    def __init__(
        self,
        provider: MarketProvider,
    ):

        self.provider = provider

    async def start(self):

        start = getattr(
            self.provider,
            "start",
            None,
        )

        if start:
            await start()

    async def close(self):

        close = getattr(
            self.provider,
            "close",
            None,
        )

        if close:
            await close()

    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "1m",
        limit: int = 200,
    ) -> list[Candle]:

        if limit < 20:

            raise ValueError(
                "Минимум 20 свечей."
            )

        if limit > 5000:

            raise ValueError(
                "Максимум 5000 свечей."
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
                "Недостаточно свечей."
            )

        return candles

    async def get_multi_timeframe(
        self,
        symbol: str,
        timeframes: tuple[str, ...] = (
            "1m",
            "5m",
            "15m",
        ),
        limit: int = 200,
    ) -> dict[
        str,
        list[Candle],
    ]:

        result = {}

        for timeframe in timeframes:

            candles = (
                await self.get_candles(
                    symbol,
                    timeframe,
                    limit,
                )
            )

            result[timeframe] = candles

        return result
