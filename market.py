from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import aiohttp


logger = logging.getLogger("market")


# ============================================================
# CONSTANTS
# ============================================================

SUPPORTED_TIMEFRAMES = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}

MIN_CANDLES = 20
MAX_CANDLES = 5000

REQUEST_TIMEOUT = 15

MAX_RETRIES = 2

RETRY_DELAY = 1.0


# ============================================================
# EXCEPTIONS
# ============================================================

class MarketDataError(Exception):
    """
    Ошибка получения или проверки
    рыночных данных.
    """

    pass


class MarketProviderError(
    MarketDataError
):
    """
    Ошибка конкретного provider.
    """

    pass


# ============================================================
# CANDLE
# ============================================================

@dataclass(slots=True)
class Candle:

    timestamp: datetime

    open: float

    high: float

    low: float

    close: float

    volume: float = 0.0

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        return self.close < self.open

    @property
    def body(self) -> float:
        return abs(
            self.close - self.open
        )

    @property
    def range(self) -> float:
        return (
            self.high - self.low
        )

    @property
    def body_ratio(self) -> float:
        candle_range = self.range

        if candle_range <= 0:
            return 0.0

        return (
            self.body
            / candle_range
        )


# ============================================================
# QUOTE
# ============================================================

@dataclass(slots=True)
class Quote:

    symbol: str

    bid: float

    ask: float

    timestamp: datetime

    @property
    def mid(self) -> float:

        return (
            self.bid
            + self.ask
        ) / 2

    @property
    def spread(self) -> float:

        return max(
            0.0,
            self.ask - self.bid,
        )

    @property
    def spread_percent(self) -> float:

        if self.mid <= 0:
            return 0.0

        return (
            self.spread
            / self.mid
            * 100
        )


# ============================================================
# PROVIDER INTERFACE
# ============================================================

class MarketProvider:

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> list[Candle]:

        raise NotImplementedError


# ============================================================
# HTTP PROVIDER
# ============================================================

class HTTPMarketProvider(
    MarketProvider
):

    """
    Универсальный HTTP provider.

    Ожидаемый ответ:

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

    Также поддерживается:

    [
        {
            "timestamp": 1234567890,
            "open": 1.1,
            "high": 1.2,
            "low": 1.0,
            "close": 1.15,
            "volume": 123
        }
    ]
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout: float = REQUEST_TIMEOUT,
    ):

        if not base_url:

            raise ValueError(
                "MARKET_API_URL не задан."
            )

        self.base_url = (
            base_url.rstrip("/")
        )

        self.api_key = api_key

        self.timeout = timeout

        self.session: (
            aiohttp.ClientSession | None
        ) = None

    # ========================================================
    # START
    # ========================================================

    async def start(self):

        if (
            self.session is not None
            and not self.session.closed
        ):
            return

        self.session = (
            aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(
                    total=self.timeout
                ),
            )
        )

        logger.info(
            "Market HTTP provider started."
        )

    # ========================================================
    # CLOSE
    # ========================================================

    async def close(self):

        if self.session:

            try:

                await self.session.close()

            finally:

                self.session = None

        logger.info(
            "Market HTTP provider closed."
        )

    # ========================================================
    # GET CANDLES
    # ========================================================

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> list[Candle]:

        self._validate_request(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
        )

        if (
            self.session is None
            or self.session.closed
        ):

            raise MarketDataError(
                "Market provider не запущен."
            )

        params = {
            "symbol": symbol,
            "timeframe": timeframe,
            "limit": limit,
        }

        headers: dict[str, str] = {
            "Accept": "application/json",
        }

        if self.api_key:

            headers["Authorization"] = (
                f"Bearer {self.api_key}"
            )

        last_error: Exception | None = None

        for attempt in range(
            MAX_RETRIES + 1
        ):

            try:

                async with self.session.get(
                    self.base_url,
                    params=params,
                    headers=headers,
                ) as response:

                    if response.status != 200:

                        body = (
                            await response.text()
                        )

                        error = (
                            f"Market API HTTP "
                            f"{response.status}: "
                            f"{body[:300]}"
                        )

                        # Retry only temporary
                        # server/rate-limit errors.
                        if (
                            response.status == 429
                            or response.status >= 500
                        ):

                            last_error = (
                                MarketProviderError(
                                    error
                                )
                            )

                            if (
                                attempt
                                < MAX_RETRIES
                            ):

                                await asyncio.sleep(
                                    RETRY_DELAY
                                    * (
                                        attempt
                                        + 1
                                    )
                                )

                                continue

                        raise MarketProviderError(
                            error
                        )

                    data = (
                        await response.json()
                    )

                candles = (
                    self._parse_candles(
                        data
                    )
                )

                candles = (
                    self._validate_candles(
                        candles,
                        timeframe,
                    )
                )

                if len(candles) < MIN_CANDLES:

                    raise MarketDataError(
                        "После проверки "
                        "осталось слишком мало "
                        "корректных свечей."
                    )

                return candles

            except (
                aiohttp.ClientConnectionError,
                aiohttp.ServerTimeoutError,
                asyncio.TimeoutError,
            ) as exc:

                last_error = exc

                if (
                    attempt
                    < MAX_RETRIES
                ):

                    await asyncio.sleep(
                        RETRY_DELAY
                        * (
                            attempt + 1
                        )
                    )

                    continue

                raise MarketDataError(
                    "Market API timeout "
                    "или ошибка подключения."
                ) from exc

            except aiohttp.ClientError as exc:

                raise MarketDataError(
                    "Ошибка подключения "
                    "к market API."
                ) from exc

        if last_error:

            raise MarketDataError(
                "Не удалось получить "
                "рыночные данные."
            ) from last_error

        raise MarketDataError(
            "Неизвестная ошибка market API."
        )

    # ========================================================
    # VALIDATE REQUEST
    # ========================================================

    @staticmethod
    def _validate_request(
        symbol: str,
        timeframe: str,
        limit: int,
    ):

        if not symbol:

            raise ValueError(
                "Symbol не может быть пустым."
            )

        if (
            timeframe
            not in SUPPORTED_TIMEFRAMES
        ):

            raise ValueError(
                "Неподдерживаемый timeframe: "
                f"{timeframe}"
            )

        if limit < MIN_CANDLES:

            raise ValueError(
                f"Минимум {MIN_CANDLES} свечей."
            )

        if limit > MAX_CANDLES:

            raise ValueError(
                f"Максимум {MAX_CANDLES} свечей."
            )

    # ========================================================
    # PARSE CANDLES
    # ========================================================

    @staticmethod
    def _parse_candles(
        data: Any,
    ) -> list[Candle]:

        if isinstance(
            data,
            dict,
        ):

            raw_candles = data.get(
                "candles"
            )

        elif isinstance(
            data,
            list,
        ):

            raw_candles = data

        else:

            raw_candles = None

        if not isinstance(
            raw_candles,
            list,
        ):

            raise MarketDataError(
                "Market API не вернул "
                "массив candles."
            )

        candles: list[Candle] = []

        for item in raw_candles:

            try:

                if not isinstance(
                    item,
                    dict,
                ):
                    continue

                timestamp = (
                    HTTPMarketProvider
                    ._parse_timestamp(
                        item[
                            "timestamp"
                        ]
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
                            0.0,
                        )
                    ),
                )

                if not (
                    candle.open > 0
                    and candle.high > 0
                    and candle.low > 0
                    and candle.close > 0
                ):

                    continue

                if candle.low > candle.high:

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

                    continue

                candles.append(
                    candle
                )

            except (
                KeyError,
                TypeError,
                ValueError,
                OverflowError,
            ):

                continue

        return candles

    # ========================================================
    # PARSE TIMESTAMP
    # ========================================================

    @staticmethod
    def _parse_timestamp(
        value: Any,
    ) -> datetime:

        if isinstance(
            value,
            datetime,
        ):

            timestamp = value

        elif isinstance(
            value,
            (int, float),
        ):

            # Unix timestamp.
            timestamp = (
                datetime.fromtimestamp(
                    float(value),
                    tz=timezone.utc,
                )
            )

        else:

            text = str(
                value
            ).strip()

            timestamp = (
                datetime.fromisoformat(
                    text.replace(
                        "Z",
                        "+00:00",
                    )
                )
            )

        if timestamp.tzinfo is None:

            timestamp = timestamp.replace(
                tzinfo=timezone.utc
            )

        return timestamp.astimezone(
            timezone.utc
        )

    # ========================================================
    # VALIDATE CANDLES
    # ========================================================

    @staticmethod
    def _validate_candles(
        candles: list[Candle],
        timeframe: str,
    ) -> list[Candle]:

        if not candles:

            raise MarketDataError(
                "Market API вернул пустой "
                "массив свечей."
            )

        interval = (
            SUPPORTED_TIMEFRAMES[
                timeframe
            ]
        )

        # ----------------------------------------------------
        # Sort
        # ----------------------------------------------------

        candles.sort(
            key=lambda candle:
                candle.timestamp
        )

        # ----------------------------------------------------
        # Remove duplicate timestamps
        # ----------------------------------------------------

        unique: dict[
            datetime,
            Candle,
        ] = {}

        for candle in candles:

            unique[
                candle.timestamp
            ] = candle

        candles = list(
            unique.values()
        )

        candles.sort(
            key=lambda candle:
                candle.timestamp
        )

        # ----------------------------------------------------
        # Remove future candles
        # ----------------------------------------------------

        now = datetime.now(
            timezone.utc
        )

        candles = [
            candle
            for candle in candles
            if candle.timestamp
            <= now
        ]

        if not candles:

            raise MarketDataError(
                "Все полученные свечи "
                "имеют будущее время."
            )

        # ----------------------------------------------------
        # Check chronological order
        # ----------------------------------------------------

        valid: list[Candle] = []

        previous: Candle | None = None

        for candle in candles:

            if previous is not None:

                delta = (
                    candle.timestamp
                    - previous.timestamp
                ).total_seconds()

                # Отбрасываем невозможные
                # отрицательные интервалы.
                if delta <= 0:
                    continue

                # Огромный gap сам по себе
                # не делает свечу неправильной,
                # поэтому просто логируем.
                if delta > interval * 3:

                    logger.warning(
                        "Large candle gap for "
                        "%s: %.0f seconds.",
                        timeframe,
                        delta,
                    )

            valid.append(
                candle
            )

            previous = candle

        if len(valid) < MIN_CANDLES:

            raise MarketDataError(
                "Недостаточно корректных "
                "свечей после валидации."
            )

        return valid


# ============================================================
# MARKET CLIENT
# ============================================================

class MarketClient:

    def __init__(
        self,
        provider: MarketProvider,
    ):

        self.provider = provider

        self.started = False

    # ========================================================
    # START
    # ========================================================

    async def start(self):

        if self.started:
            return

        start = getattr(
            self.provider,
            "start",
            None,
        )

        if start:

            await start()

        self.started = True

        logger.info(
            "Market client started."
        )

    # ========================================================
    # CLOSE
    # ========================================================

    async def close(self):

        if not self.started:
            return

        close = getattr(
            self.provider,
            "close",
            None,
        )

        if close:

            await close()

        self.started = False

        logger.info(
            "Market client closed."
        )

    # ========================================================
    # GET CANDLES
    # ========================================================

    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "1m",
        limit: int = 200,
    ) -> list[Candle]:

        if (
            timeframe
            not in SUPPORTED_TIMEFRAMES
        ):

            raise ValueError(
                "Неподдерживаемый timeframe: "
                f"{timeframe}"
            )

        if limit < MIN_CANDLES:

            raise ValueError(
                f"Минимум {MIN_CANDLES} свечей."
            )

        if limit > MAX_CANDLES:

            raise ValueError(
                f"Максимум {MAX_CANDLES} свечей."
            )

        if not self.started:

            raise MarketDataError(
                "MarketClient не запущен."
            )

        candles = (
            await self.provider.get_candles(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
            )
        )

        if len(candles) < MIN_CANDLES:

            raise MarketDataError(
                "Market provider вернул "
                "недостаточно свечей."
            )

        return candles

    # ========================================================
    # MULTI TIMEFRAME
    # ========================================================

    async def get_multi_timeframe(
        self,
        symbol: str,
        timeframes: tuple[
            str,
            ...
        ] = (
            "1m",
            "5m",
            "15m",
        ),
        limit: int = 200,
    ) -> dict[
        str,
        list[Candle],
    ]:

        if not timeframes:

            raise ValueError(
                "Список timeframe пуст."
            )

        result: dict[
            str,
            list[Candle],
        ] = {}

        for timeframe in timeframes:

            candles = (
                await self.get_candles(
                    symbol=symbol,
                    timeframe=timeframe,
                    limit=limit,
                )
            )

            result[
                timeframe
            ] = candles

        return result
