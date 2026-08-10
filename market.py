from __future__ import annotations

import asyncio
import logging
import time
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


class MarketRateLimitError(MarketDataError):
    """Рынок временно ограничил количество API-запросов."""


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
# INTERNAL CACHE MODEL
# =========================================================


@dataclass(slots=True)
class _CandleCacheEntry:
    candles: list[Candle]
    created_at: float
    expires_at: float


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
# TWELVE DATA HTTP PROVIDER
# =========================================================


class HTTPMarketProvider(MarketProvider):
    """
    HTTP-провайдер для Twelve Data.

    Twelve Data ожидает параметры:

        symbol
        interval
        outputsize
        apikey

    Например:

        https://api.twelvedata.com/time_series

    API key передаётся через:

        ?apikey=YOUR_KEY

    =====================================================
    ДОПОЛНИТЕЛЬНО:
    =====================================================

    Провайдер содержит:

    - локальный cache свечей;
    - TTL для разных таймфреймов;
    - ограничение количества HTTP-запросов;
    - защиту от параллельных одинаковых запросов;
    - обработку HTTP 429;
    - использование последнего cache при временном rate limit.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout: int = 15,
        cache_ttl: float = 15.0,
        max_requests_per_minute: int = 7,
    ) -> None:
        self.base_url = base_url.rstrip("/")

        self.api_key = (
            api_key.strip()
            if isinstance(api_key, str)
            else None
        )

        self.timeout = timeout

        # -------------------------------------------------
        # CACHE
        # -------------------------------------------------

        self.cache_ttl = max(
            0.0,
            float(cache_ttl),
        )

        self._cache: dict[
            tuple[str, str, int],
            _CandleCacheEntry,
        ] = {}

        self._cache_lock = asyncio.Lock()

        # -------------------------------------------------
        # REQUEST DEDUPLICATION
        # -------------------------------------------------

        self._request_locks: dict[
            tuple[str, str, int],
            asyncio.Lock,
        ] = {}

        self._request_locks_guard = asyncio.Lock()

        # -------------------------------------------------
        # RATE LIMIT
        # -------------------------------------------------

        # Twelve Data в логах пользователя:
        #
        # limit = 8 requests/minute.
        #
        # Используем 7, чтобы оставить небольшой запас.
        self.max_requests_per_minute = max(
            1,
            int(max_requests_per_minute),
        )

        self._request_timestamps: list[float] = []

        self._rate_limit_lock = asyncio.Lock()

        # -------------------------------------------------
        # LAST RATE LIMIT
        # -------------------------------------------------

        self._rate_limited_until: float = 0.0

        # -------------------------------------------------
        # HTTP SESSION
        # -------------------------------------------------

        self.session: (
            aiohttp.ClientSession | None
        ) = None

    # =====================================================
    # START
    # =====================================================

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

        if not self.api_key:
            logger.warning(
                "MARKET_API_KEY is empty. "
                "Twelve Data requests will fail with HTTP 401."
            )

    # =====================================================
    # CLOSE
    # =====================================================

    async def close(self) -> None:
        if self.session is not None:
            await self.session.close()
            self.session = None

        async with self._cache_lock:
            self._cache.clear()

        async with self._request_locks_guard:
            self._request_locks.clear()

        async with self._rate_limit_lock:
            self._request_timestamps.clear()
            self._rate_limited_until = 0.0

        logger.info(
            "HTTP market provider closed."
        )

    # =====================================================
    # NORMALIZE SYMBOL
    # =====================================================

    @staticmethod
    def _normalize_symbol(
        symbol: str,
    ) -> str:
        symbol = str(symbol).strip().upper()

        if not symbol:
            raise ValueError(
                "Symbol is required."
            )

        # Twelve Data обычно принимает:
        #
        # EUR/USD
        #
        # Если где-то передали:
        #
        # EURUSD
        #
        # превращаем в:
        #
        # EUR/USD

        if (
            "/" not in symbol
            and len(symbol) == 6
            and symbol.isalpha()
        ):
            symbol = (
                f"{symbol[:3]}/"
                f"{symbol[3:]}"
            )

        return symbol

    # =====================================================
    # NORMALIZE TIMEFRAME
    # =====================================================

    @staticmethod
    def _normalize_timeframe(
        timeframe: str,
    ) -> str:
        timeframe = (
            str(timeframe)
            .strip()
            .lower()
        )

        if not timeframe:
            raise ValueError(
                "Timeframe is required."
            )

        aliases = {
            "1m": "1min",
            "5m": "5min",
            "15m": "15min",
            "30m": "30min",
            "45m": "45min",
            "1h": "1h",
            "2h": "2h",
            "4h": "4h",
            "8h": "8h",
            "1d": "1day",
            "1w": "1week",
            "1mo": "1month",

            "1min": "1min",
            "5min": "5min",
            "15min": "15min",
            "30min": "30min",
            "45min": "45min",

            "1hour": "1h",
            "2hour": "2h",
            "4hour": "4h",
            "8hour": "8h",

            "day": "1day",
            "week": "1week",
            "month": "1month",
        }

        return aliases.get(
            timeframe,
            timeframe,
        )

    # =====================================================
    # CACHE TTL
    # =====================================================

    def _get_cache_ttl(
        self,
        timeframe: str,
    ) -> float:
        """
        Возвращает TTL кэша в секундах.

        Для более быстрых таймфреймов cache
        обновляется чаще.

        При этом мы НЕ запрашиваем Twelve Data
        на каждом цикле scheduler.
        """

        normalized = (
            self._normalize_timeframe(
                timeframe
            )
        )

        if normalized == "1min":
            return max(
                self.cache_ttl,
                20.0,
            )

        if normalized == "5min":
            return max(
                self.cache_ttl,
                45.0,
            )

        if normalized == "15min":
            return max(
                self.cache_ttl,
                90.0,
            )

        if normalized in {
            "30min",
            "45min",
        }:
            return max(
                self.cache_ttl,
                120.0,
            )

        if normalized in {
            "1h",
            "2h",
            "4h",
            "8h",
        }:
            return max(
                self.cache_ttl,
                180.0,
            )

        if normalized in {
            "1day",
            "1week",
            "1month",
        }:
            return max(
                self.cache_ttl,
                300.0,
            )

        return max(
            self.cache_ttl,
            30.0,
        )

    # =====================================================
    # CACHE KEY
    # =====================================================

    def _cache_key(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> tuple[str, str, int]:
        return (
            self._normalize_symbol(symbol),
            self._normalize_timeframe(timeframe),
            int(limit),
        )

    # =====================================================
    # GET CACHE
    # =====================================================

    async def _get_cached_candles(
        self,
        key: tuple[str, str, int],
        allow_expired: bool = False,
    ) -> list[Candle] | None:
        now = time.monotonic()

        async with self._cache_lock:
            entry = self._cache.get(key)

            if entry is None:
                return None

            if (
                not allow_expired
                and now >= entry.expires_at
            ):
                return None

            # Копия списка нужна, чтобы внешний код
            # случайно не испортил cache.
            return list(entry.candles)

    # =====================================================
    # SAVE CACHE
    # =====================================================

    async def _save_cached_candles(
        self,
        key: tuple[str, str, int],
        candles: list[Candle],
        ttl: float,
    ) -> None:
        now = time.monotonic()

        entry = _CandleCacheEntry(
            candles=list(candles),
            created_at=now,
            expires_at=now + ttl,
        )

        async with self._cache_lock:
            self._cache[key] = entry

    # =====================================================
    # GET REQUEST LOCK
    # =====================================================

    async def _get_request_lock(
        self,
        key: tuple[str, str, int],
    ) -> asyncio.Lock:
        async with self._request_locks_guard:
            lock = self._request_locks.get(key)

            if lock is None:
                lock = asyncio.Lock()
                self._request_locks[key] = lock

            return lock

    # =====================================================
    # RATE LIMIT CLEANUP
    # =====================================================

    async def _cleanup_request_timestamps(
        self,
        now: float,
    ) -> None:
        border = now - 60.0

        self._request_timestamps = [
            timestamp
            for timestamp in self._request_timestamps
            if timestamp > border
        ]

    # =====================================================
    # WAIT FOR RATE LIMIT SLOT
    # =====================================================

    async def _wait_for_rate_limit_slot(
        self,
    ) -> None:
        """
        Локальный rate limiter.

        Мы намеренно держим лимит ниже официального
        значения из ошибки Twelve Data.

        Например:

            Twelve Data = 8/min
            local limit = 7/min

        Это оставляет один запрос запаса.
        """

        while True:
            async with self._rate_limit_lock:
                now = time.monotonic()

                # -------------------------------------------------
                # Если Twelve Data недавно ответил 429,
                # ждём до окончания cooldown.
                # -------------------------------------------------

                if now < self._rate_limited_until:
                    wait_for = (
                        self._rate_limited_until
                        - now
                    )

                else:
                    await self._cleanup_request_timestamps(
                        now
                    )

                    if (
                        len(self._request_timestamps)
                        < self.max_requests_per_minute
                    ):
                        self._request_timestamps.append(
                            now
                        )
                        return

                    oldest = min(
                        self._request_timestamps
                    )

                    wait_for = max(
                        0.1,
                        60.0
                        - (
                            now
                            - oldest
                        ),
                    )

            logger.warning(
                "Market API rate limiter waiting %.1f seconds.",
                wait_for,
            )

            await asyncio.sleep(
                wait_for
            )

    # =====================================================
    # REGISTER API RATE LIMIT
    # =====================================================

    async def _register_rate_limit(
        self,
        cooldown: float = 60.0,
    ) -> None:
        async with self._rate_limit_lock:
            self._rate_limited_until = max(
                self._rate_limited_until,
                time.monotonic()
                + max(
                    1.0,
                    cooldown,
                ),
            )

    # =====================================================
    # BUILD PARAMS
    # =====================================================

    def _build_params(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> dict[str, Any]:
        if not self.api_key:
            raise MarketDataError(
                "MARKET_API_KEY не задан. "
                "Добавь API key Twelve Data "
                "в Environment Variables Render."
            )

        normalized_symbol = (
            self._normalize_symbol(symbol)
        )

        normalized_interval = (
            self._normalize_timeframe(
                timeframe
            )
        )

        return {
            "symbol": normalized_symbol,
            "interval": normalized_interval,
            "outputsize": limit,
            "apikey": self.api_key,
            "format": "JSON",
        }

    # =====================================================
    # GET CANDLES
    # =====================================================

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

        if limit < 20:
            raise ValueError(
                "At least 20 candles are required."
            )

        if limit > 5000:
            raise ValueError(
                "Maximum candle limit is 5000."
            )

        normalized_symbol = (
            self._normalize_symbol(symbol)
        )

        normalized_timeframe = (
            self._normalize_timeframe(
                timeframe
            )
        )

        key = (
            normalized_symbol,
            normalized_timeframe,
            int(limit),
        )

        # =================================================
        # 1. FRESH CACHE
        # =================================================

        cached = await self._get_cached_candles(
            key,
            allow_expired=False,
        )

        if cached is not None:
            logger.debug(
                "Market cache HIT: "
                "symbol=%s timeframe=%s limit=%s",
                normalized_symbol,
                normalized_timeframe,
                limit,
            )

            return cached

        logger.debug(
            "Market cache MISS: "
            "symbol=%s timeframe=%s limit=%s",
            normalized_symbol,
            normalized_timeframe,
            limit,
        )

        # =================================================
        # 2. REQUEST DEDUPLICATION
        # =================================================

        request_lock = (
            await self._get_request_lock(
                key
            )
        )

        async with request_lock:
            # -------------------------------------------------
            # После ожидания lock другой coroutine могла
            # уже загрузить данные.
            # Проверяем cache ещё раз.
            # -------------------------------------------------

            cached = await self._get_cached_candles(
                key,
                allow_expired=False,
            )

            if cached is not None:
                logger.debug(
                    "Market cache HIT after lock: "
                    "symbol=%s timeframe=%s",
                    normalized_symbol,
                    normalized_timeframe,
                )

                return cached

            # =================================================
            # 3. BUILD REQUEST
            # =================================================

            params = self._build_params(
                symbol=normalized_symbol,
                timeframe=normalized_timeframe,
                limit=limit,
            )

            logger.debug(
                "Request candles: "
                "symbol=%s timeframe=%s limit=%s",
                params["symbol"],
                params["interval"],
                limit,
            )

            # =================================================
            # 4. RATE LIMIT
            # =================================================

            await self._wait_for_rate_limit_slot()

            try:
                async with self.session.get(
                    self.base_url,
                    params=params,
                ) as response:
                    body = await response.text()

                    logger.debug(
                        "Market API response: "
                        "status=%s symbol=%s timeframe=%s",
                        response.status,
                        params["symbol"],
                        params["interval"],
                    )

                    # -----------------------------------------
                    # HTTP 429
                    # -----------------------------------------

                    if response.status == 429:
                        await self._register_rate_limit(
                            cooldown=60.0
                        )

                        # -------------------------------------
                        # Очень важно:
                        #
                        # Если есть старый cache, возвращаем
                        # его вместо полного падения анализа.
                        # -------------------------------------

                        stale = (
                            await self._get_cached_candles(
                                key,
                                allow_expired=True,
                            )
                        )

                        if stale is not None:
                            logger.warning(
                                "Market API rate limited "
                                "for %s %s. "
                                "Using stale cache.",
                                normalized_symbol,
                                normalized_timeframe,
                            )

                            return stale

                        raise MarketRateLimitError(
                            "Market API returned HTTP 429: "
                            f"{body[:1000]}"
                        )

                    # -----------------------------------------
                    # OTHER HTTP ERRORS
                    # -----------------------------------------

                    if response.status != 200:
                        raise MarketDataError(
                            "Market API returned HTTP "
                            f"{response.status}: "
                            f"{body[:1000]}"
                        )

                    # -----------------------------------------
                    # JSON
                    # -----------------------------------------

                    try:
                        data = await response.json(
                            content_type=None
                        )

                    except Exception as exc:
                        raise MarketDataError(
                            "Market API returned "
                            "invalid JSON: "
                            f"{body[:500]}"
                        ) from exc

            except asyncio.TimeoutError as exc:
                # ---------------------------------------------
                # Timeout.
                #
                # Если есть старый cache — лучше использовать
                # его.
                # ---------------------------------------------

                stale = (
                    await self._get_cached_candles(
                        key,
                        allow_expired=True,
                    )
                )

                if stale is not None:
                    logger.warning(
                        "Market API timeout for %s %s. "
                        "Using stale cache.",
                        normalized_symbol,
                        normalized_timeframe,
                    )

                    return stale

                raise MarketDataError(
                    "Market API timeout."
                ) from exc

            except aiohttp.ClientError as exc:
                stale = (
                    await self._get_cached_candles(
                        key,
                        allow_expired=True,
                    )
                )

                if stale is not None:
                    logger.warning(
                        "Market API connection error "
                        "for %s %s. "
                        "Using stale cache: %s",
                        normalized_symbol,
                        normalized_timeframe,
                        exc,
                    )

                    return stale

                raise MarketDataError(
                    "Market API connection error: "
                    f"{exc}"
                ) from exc

            # =================================================
            # 5. TWELVE DATA ERROR RESPONSE
            # =================================================

            if isinstance(data, dict):
                status = str(
                    data.get(
                        "status",
                        "",
                    )
                ).lower()

                if status == "error":
                    code = data.get(
                        "code",
                        "unknown",
                    )

                    message = data.get(
                        "message",
                        "Unknown Twelve Data error.",
                    )

                    # -----------------------------------------
                    # Twelve Data иногда возвращает 429
                    # внутри JSON даже при HTTP 200.
                    # -----------------------------------------

                    if str(code) == "429":
                        await self._register_rate_limit(
                            cooldown=60.0
                        )

                        stale = (
                            await self._get_cached_candles(
                                key,
                                allow_expired=True,
                            )
                        )

                        if stale is not None:
                            logger.warning(
                                "Twelve Data rate limit "
                                "for %s %s. "
                                "Using stale cache.",
                                normalized_symbol,
                                normalized_timeframe,
                            )

                            return stale

                        raise MarketRateLimitError(
                            "Twelve Data rate limit "
                            f"{code}: {message}"
                        )

                    raise MarketDataError(
                        "Twelve Data error "
                        f"{code}: {message}"
                    )

            # =================================================
            # 6. PARSE
            # =================================================

            candles = self._parse_candles(
                data
            )

            # =================================================
            # 7. SAVE CACHE
            # =================================================

            ttl = self._get_cache_ttl(
                normalized_timeframe
            )

            await self._save_cached_candles(
                key=key,
                candles=candles,
                ttl=ttl,
            )

            logger.debug(
                "Market cache UPDATED: "
                "symbol=%s timeframe=%s candles=%s ttl=%.1fs",
                normalized_symbol,
                normalized_timeframe,
                len(candles),
                ttl,
            )

            return list(candles)

    # =====================================================
    # PARSE CANDLES
    # =====================================================

    @staticmethod
    def _parse_candles(
        data: Any,
    ) -> list[Candle]:
        if not isinstance(
            data,
            dict,
        ):
            raise MarketDataError(
                "Market response is not a JSON object."
            )

        # =================================================
        # TWELVE DATA FORMAT
        # =================================================

        raw = data.get(
            "values"
        )

        # =================================================
        # FALLBACK FORMATS
        # =================================================

        if raw is None:
            raw = data.get(
                "candles"
            )

        if raw is None:
            raw = data.get(
                "data"
            )

        if raw is None:
            raw = data.get(
                "results"
            )

        if not isinstance(
            raw,
            list,
        ):
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
                # =============================================
                # TIMESTAMP
                # =============================================

                timestamp = item.get(
                    "datetime"
                )

                if timestamp is None:
                    timestamp = item.get(
                        "timestamp"
                    )

                if timestamp is None:
                    timestamp = item.get(
                        "time"
                    )

                if timestamp is None:
                    continue

                timestamp = (
                    HTTPMarketProvider._parse_timestamp(
                        timestamp
                    )
                )

                # =============================================
                # OHLC
                # =============================================

                open_raw = item.get(
                    "open"
                )

                high_raw = item.get(
                    "high"
                )

                low_raw = item.get(
                    "low"
                )

                close_raw = item.get(
                    "close"
                )

                if (
                    open_raw is None
                    or high_raw is None
                    or low_raw is None
                    or close_raw is None
                ):
                    continue

                open_price = float(
                    open_raw
                )

                high_price = float(
                    high_raw
                )

                low_price = float(
                    low_raw
                )

                close_price = float(
                    close_raw
                )

                # =============================================
                # VOLUME
                # =============================================

                volume_raw = item.get(
                    "volume",
                    0,
                )

                if volume_raw in (
                    None,
                    "",
                ):
                    volume = 0.0

                else:
                    volume = float(
                        volume_raw
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
                OverflowError,
            ):
                continue

            # =============================================
            # VALIDATION
            # =============================================

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

            result.append(
                candle
            )

        # =================================================
        # SORT
        # =================================================

        result.sort(
            key=lambda item: item.timestamp
        )

        # =================================================
        # VALIDATION
        # =================================================

        if len(result) < 20:
            raise MarketDataError(
                "Too few valid candles: "
                f"{len(result)}."
            )

        return result

    # =====================================================
    # PARSE TIMESTAMP
    # =====================================================

    @staticmethod
    def _parse_timestamp(
        value: Any,
    ) -> datetime:
        # =================================================
        # DATETIME
        # =================================================

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

        # =================================================
        # UNIX TIMESTAMP
        # =================================================

        if isinstance(
            value,
            (int, float),
        ):
            numeric = float(
                value
            )

            # milliseconds
            if numeric > 10_000_000_000:
                numeric /= 1000

            return datetime.fromtimestamp(
                numeric,
                tz=timezone.utc,
            )

        text = str(
            value
        ).strip()

        if not text:
            raise ValueError(
                "Empty timestamp."
            )

        # =================================================
        # ISO-8601
        # =================================================

        normalized = text.replace(
            "Z",
            "+00:00",
        )

        try:
            timestamp = (
                datetime.fromisoformat(
                    normalized
                )
            )

        except ValueError:
            # =============================================
            # Unix timestamp string
            # =============================================

            try:
                numeric = float(
                    text
                )

            except ValueError as exc:
                raise ValueError(
                    f"Unsupported timestamp: {text}"
                ) from exc

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

    # =====================================================
    # START
    # =====================================================

    async def start(self) -> None:
        await self.provider.start()

        logger.info(
            "Market client started."
        )

    # =====================================================
    # CLOSE
    # =====================================================

    async def close(self) -> None:
        await self.provider.close()

        logger.info(
            "Market client closed."
        )

    # =====================================================
    # GET CANDLES
    # =====================================================

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

    # =====================================================
    # MULTI TIMEFRAME
    # =====================================================

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

    # =====================================================
    # SAFE MULTI TIMEFRAME
    # =====================================================

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
    "MarketRateLimitError",
    "MarketProvider",
    "HTTPMarketProvider",
    "MarketClient",
]
