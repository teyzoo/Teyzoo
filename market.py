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
    """API временно ограничил количество запросов."""
class MarketDailyLimitError(MarketRateLimitError):
    """
    Дневной лимит API исчерпан.
    После такой ошибки провайдер блокирует новые запросы
    до следующего UTC-дня или до ручного сброса cooldown.
    """
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
        return (self.bid + self.ask) / 2.0
# =========================================================
# CACHE MODEL
# =========================================================
@dataclass(slots=True)
class _CandleCacheEntry:
    candles: list[Candle]
    created_at: float
    expires_at: float
# =========================================================
# PROVIDER
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
# HTTP MARKET PROVIDER
# =========================================================
class HTTPMarketProvider(MarketProvider):
    """
    Twelve Data HTTP provider.
    Основные возможности:
    - многоуровневый cache;
    - TTL по timeframe;
    - request deduplication;
    - локальный rate limiter;
    - защита от дневного лимита;
    - cooldown после 429;
    - stale cache;
    - безопасный JSON parsing;
    - защита от одновременных одинаковых запросов;
    - совместимость с MarketClient.
    """
    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout: int = 15,
        cache_ttl: float = 15.0,
        max_requests_per_minute: int = 5,
        daily_request_limit: int = 760,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = (
            api_key.strip()
            if isinstance(api_key, str)
            else None
        )
        self.timeout = max(
            5,
            int(timeout),
        )
        self.cache_ttl = max(
            5.0,
            float(cache_ttl),
        )
        # Не позволяем конфигурации случайно
        # создавать слишком много запросов.
        self.max_requests_per_minute = max(
            1,
            min(
                int(max_requests_per_minute),
                10,
            ),
        )
        # Это не точный лимит Twelve Data,
        # а внутренний safety limit.
        #
        # Например:
        # Twelve Data = 800/day
        # наш safety limit = 760/day
        #
        # Оставляем небольшой запас.
        self.daily_request_limit = max(
            100,
            int(daily_request_limit),
        )
        # =================================================
        # CACHE
        # =================================================
        self._cache: dict[
            tuple[str, str, int],
            _CandleCacheEntry,
        ] = {}
        self._cache_lock = asyncio.Lock()
        # =================================================
        # REQUEST DEDUPLICATION
        # =================================================
        self._request_locks: dict[
            tuple[str, str, int],
            asyncio.Lock,
        ] = {}
        self._request_locks_guard = asyncio.Lock()
        # =================================================
        # RATE LIMIT
        # =================================================
        self._request_timestamps: list[float] = []
        self._rate_limit_lock = asyncio.Lock()
        self._rate_limited_until: float = 0.0
        # =================================================
        # DAILY LIMIT
        # =================================================
        self._daily_request_count: int = 0
        self._daily_counter_date: str = (
            self._utc_date_key()
        )
        self._daily_limit_until: float = 0.0
        # =================================================
        # HTTP
        # =================================================
        self.session: (
            aiohttp.ClientSession | None
        ) = None
        self._started = False
    # =====================================================
    # UTC DATE
    # =====================================================
    @staticmethod
    def _utc_date_key() -> str:
        return datetime.now(
            timezone.utc
        ).strftime("%Y-%m-%d")
    # =====================================================
    # START
    # =====================================================
    async def start(self) -> None:
        if self.session is not None:
            return
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(
                total=self.timeout,
            ),
            raise_for_status=False,
        )
        self._started = True
        logger.info(
            "HTTP market provider started."
        )
        logger.info(
            "Market limits: %s requests/minute, "
            "%s safety requests/day.",
            self.max_requests_per_minute,
            self.daily_request_limit,
        )
        if not self.api_key:
            logger.warning(
                "MARKET_API_KEY is empty."
            )
    # =====================================================
    # CLOSE
    # =====================================================
    async def close(self) -> None:
        if self.session is not None:
            await self.session.close()
        self.session = None
        self._started = False
        async with self._cache_lock:
            self._cache.clear()
        async with self._request_locks_guard:
            self._request_locks.clear()
        async with self._rate_limit_lock:
            self._request_timestamps.clear()
            self._rate_limited_until = 0.0
        self._daily_request_count = 0
        self._daily_limit_until = 0.0
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
        symbol = str(
            symbol
        ).strip().upper()
        if not symbol:
            raise ValueError(
                "Symbol is required."
            )
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
            "1min": "1min",
            "5min": "5min",
            "15min": "15min",
            "30min": "30min",
            "45min": "45min",
            "1h": "1h",
            "2h": "2h",
            "4h": "4h",
            "8h": "8h",
            "1hour": "1h",
            "2hour": "2h",
            "4hour": "4h",
            "8hour": "8h",
            "1d": "1day",
            "day": "1day",
            "1w": "1week",
            "week": "1week",
            "1mo": "1month",
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
        normalized = (
            self._normalize_timeframe(
                timeframe
            )
        )
        # -------------------------------------------------
        # 1 MINUTE
        # -------------------------------------------------
        if normalized == "1min":
            return max(
                self.cache_ttl,
                45.0,
            )
        # -------------------------------------------------
        # 5 MINUTES
        # -------------------------------------------------
        if normalized == "5min":
            return max(
                self.cache_ttl,
                90.0,
            )
        # -------------------------------------------------
        # 15 MINUTES
        # -------------------------------------------------
        if normalized == "15min":
            return max(
                self.cache_ttl,
                180.0,
            )
        # -------------------------------------------------
        # 30 / 45
        # -------------------------------------------------
        if normalized in {
            "30min",
            "45min",
        }:
            return max(
                self.cache_ttl,
                300.0,
            )
        # -------------------------------------------------
        # HOURS
        # -------------------------------------------------
        if normalized in {
            "1h",
            "2h",
            "4h",
            "8h",
        }:
            return max(
                self.cache_ttl,
                600.0,
            )
        # -------------------------------------------------
        # DAYS
        # -------------------------------------------------
        if normalized in {
            "1day",
            "1week",
            "1month",
        }:
            return max(
                self.cache_ttl,
                1200.0,
            )
        return max(
            self.cache_ttl,
            120.0,
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
            entry = self._cache.get(
                key
            )
            if entry is None:
                return None
            if (
                not allow_expired
                and now >= entry.expires_at
            ):
                return None
            return list(
                entry.candles
            )
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
    # REQUEST LOCK
    # =====================================================
    async def _get_request_lock(
        self,
        key: tuple[str, str, int],
    ) -> asyncio.Lock:
        async with self._request_locks_guard:
            lock = self._request_locks.get(
                key
            )
            if lock is None:
                lock = asyncio.Lock()
                self._request_locks[key] = (
                    lock
                )
            return lock
    # =====================================================
    # CLEAN RATE LIMIT
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
    # DAILY COUNTER
    # =====================================================
    async def _refresh_daily_counter(
        self,
    ) -> None:
        current_date = self._utc_date_key()
        if current_date != self._daily_counter_date:
            self._daily_counter_date = (
                current_date
            )
            self._daily_request_count = 0
            self._daily_limit_until = 0.0
            logger.info(
                "Daily market API counter reset."
            )
    # =====================================================
    # DAILY LIMIT CHECK
    # =====================================================
    async def _check_daily_limit(
        self,
    ) -> None:
        await self._refresh_daily_counter()
        now = time.monotonic()
        if (
            now
            < self._daily_limit_until
        ):
            raise MarketDailyLimitError(
                "Market API daily limit "
                "cooldown is active."
            )
        if (
            self._daily_request_count
            >= self.daily_request_limit
        ):
            # До следующего UTC дня.
            tomorrow = (
                datetime.now(
                    timezone.utc
                )
                .replace(
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
                .timestamp()
                + 86400
            )
            seconds_until_reset = max(
                60.0,
                tomorrow
                - time.time(),
            )
            self._daily_limit_until = (
                now
                + seconds_until_reset
            )
            logger.error(
                "Internal daily market API "
                "safety limit reached: %s/%s. "
                "New API requests disabled "
                "until next UTC day.",
                self._daily_request_count,
                self.daily_request_limit,
            )
            raise MarketDailyLimitError(
                "Internal daily market API "
                "safety limit reached."
            )
    # =====================================================
    # REGISTER REQUEST
    # =====================================================
    async def _register_request(
        self,
    ) -> None:
        await self._check_daily_limit()
        self._daily_request_count += 1
        logger.debug(
            "Market API request counter: %s/%s",
            self._daily_request_count,
            self.daily_request_limit,
        )
    # =====================================================
    # RATE LIMIT WAIT
    # =====================================================
    async def _wait_for_rate_limit_slot(
        self,
    ) -> None:
        while True:
            async with self._rate_limit_lock:
                now = time.monotonic()
                # -------------------------------------------------
                # DAILY LIMIT COOLDOWN
                # -------------------------------------------------
                if (
                    now
                    < self._daily_limit_until
                ):
                    wait_for = (
                        self._daily_limit_until
                        - now
                    )
                # -------------------------------------------------
                # NORMAL API COOLDOWN
                # -------------------------------------------------
                elif (
                    now
                    < self._rate_limited_until
                ):
                    wait_for = (
                        self._rate_limited_until
                        - now
                    )
                else:
                    await (
                        self._cleanup_request_timestamps(
                            now
                        )
                    )
                    if (
                        len(
                            self._request_timestamps
                        )
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
            # -------------------------------------------------
            # DO NOT SLEEP FOR A WHOLE DAY
            #
            # Если дневной cooldown активен,
            # вызывающая функция получит ошибку
            # через _check_daily_limit().
            # -------------------------------------------------
            if (
                wait_for
                >= 3600
            ):
                raise MarketDailyLimitError(
                    "Market API daily cooldown active."
                )
            logger.warning(
                "Market API rate limiter "
                "waiting %.1f seconds.",
                wait_for,
            )
            await asyncio.sleep(
                wait_for
            )
    # =====================================================
    # REGISTER 429
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
    # REGISTER DAILY LIMIT
    # =====================================================
    async def _register_daily_limit(
        self,
    ) -> None:
        now = time.monotonic()
        tomorrow = (
            datetime.now(
                timezone.utc
            )
            .replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            .timestamp()
            + 86400
        )
        seconds_until_reset = max(
            60.0,
            tomorrow
            - time.time(),
        )
        self._daily_limit_until = (
            now
            + seconds_until_reset
        )
        logger.error(
            "Twelve Data daily API limit "
            "reached. New market requests "
            "disabled for %.1f hours.",
            seconds_until_reset / 3600.0,
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
                "MARKET_API_KEY не задан."
            )
        return {
            "symbol": self._normalize_symbol(
                symbol
            ),
            "interval": self._normalize_timeframe(
                timeframe
            ),
            "outputsize": int(limit),
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
        key = self._cache_key(
            symbol,
            timeframe,
            limit,
        )
        normalized_symbol = key[0]
        normalized_timeframe = key[1]
        # =================================================
        # 1. FRESH CACHE
        # =================================================
        cached = (
            await self._get_cached_candles(
                key,
                allow_expired=False,
            )
        )
        if cached is not None:
            logger.debug(
                "CACHE HIT | %s | %s | %s",
                normalized_symbol,
                normalized_timeframe,
                limit,
            )
            return cached
        # =================================================
        # 2. REQUEST LOCK
        # =================================================
        request_lock = (
            await self._get_request_lock(
                key
            )
        )
        async with request_lock:
            # -------------------------------------------------
            # Another coroutine may have loaded
            # the same data.
            # -------------------------------------------------
            cached = (
                await self._get_cached_candles(
                    key,
                    allow_expired=False,
                )
            )
            if cached is not None:
                logger.debug(
                    "CACHE HIT AFTER LOCK | "
                    "%s | %s",
                    normalized_symbol,
                    normalized_timeframe,
                )
                return cached
            # =================================================
            # 3. CHECK DAILY LIMIT BEFORE API REQUEST
            # =================================================
            try:
                await self._check_daily_limit()
            except MarketDailyLimitError:
                stale = (
                    await self._get_cached_candles(
                        key,
                        allow_expired=True,
                    )
                )
                if stale is not None:
                    logger.warning(
                        "DAILY LIMIT | "
                        "%s | %s | "
                        "USING STALE CACHE",
                        normalized_symbol,
                        normalized_timeframe,
                    )
                    return stale
                raise
            # =================================================
            # 4. BUILD REQUEST
            # =================================================
            params = self._build_params(
                normalized_symbol,
                normalized_timeframe,
                limit,
            )
            # =================================================
            # 5. RATE LIMIT
            # =================================================
            try:
                await (
                    self._wait_for_rate_limit_slot()
                )
            except MarketDailyLimitError:
                stale = (
                    await self._get_cached_candles(
                        key,
                        allow_expired=True,
                    )
                )
                if stale is not None:
                    logger.warning(
                        "DAILY COOLDOWN | "
                        "%s | %s | "
                        "USING STALE CACHE",
                        normalized_symbol,
                        normalized_timeframe,
                    )
                    return stale
                raise
            # =================================================
            # 6. REGISTER API REQUEST
            # =================================================
            try:
                await self._register_request()
            except MarketDailyLimitError:
                stale = (
                    await self._get_cached_candles(
                        key,
                        allow_expired=True,
                    )
                )
                if stale is not None:
                    logger.warning(
                        "DAILY SAFETY LIMIT | "
                        "%s | %s | "
                        "USING STALE CACHE",
                        normalized_symbol,
                        normalized_timeframe,
                    )
                    return stale
                raise
            # =================================================
            # 7. HTTP REQUEST
            # =================================================
            try:
                async with self.session.get(
                    self.base_url,
                    params=params,
                ) as response:
                    body = await response.text()
                    logger.debug(
                        "API RESPONSE | "
                        "status=%s | "
                        "%s | %s",
                        response.status,
                        normalized_symbol,
                        normalized_timeframe,
                    )
                    # =================================================
                    # HTTP 429
                    # =================================================
                    if response.status == 429:
                        await self._register_rate_limit(
                            60.0
                        )
                        stale = (
                            await self._get_cached_candles(
                                key,
                                allow_expired=True,
                            )
                        )
                        if stale is not None:
                            logger.warning(
                                "HTTP 429 | "
                                "%s | %s | "
                                "USING STALE CACHE",
                                normalized_symbol,
                                normalized_timeframe,
                            )
                            return stale
                        raise MarketRateLimitError(
                            "Market API returned HTTP 429: "
                            f"{body[:1000]}"
                        )
                    # =================================================
                    # OTHER HTTP ERRORS
                    # =================================================
                    if response.status != 200:
                        stale = (
                            await self._get_cached_candles(
                                key,
                                allow_expired=True,
                            )
                        )
                        if stale is not None:
                            logger.warning(
                                "HTTP ERROR %s | "
                                "%s | %s | "
                                "USING STALE CACHE",
                                response.status,
                                normalized_symbol,
                                normalized_timeframe,
                            )
                            return stale
                        raise MarketDataError(
                            "Market API returned HTTP "
                            f"{response.status}: "
                            f"{body[:1000]}"
                        )
                    # =================================================
                    # JSON
                    # =================================================
                    try:
                        data = await response.json(
                            content_type=None
                        )
                    except Exception as exc:
                        stale = (
                            await self._get_cached_candles(
                                key,
                                allow_expired=True,
                            )
                        )
                        if stale is not None:
                            logger.warning(
                                "INVALID JSON | "
                                "%s | %s | "
                                "USING STALE CACHE",
                                normalized_symbol,
                                normalized_timeframe,
                            )
                            return stale
                        raise MarketDataError(
                            "Market API returned "
                            "invalid JSON."
                        ) from exc
            except asyncio.TimeoutError as exc:
                stale = (
                    await self._get_cached_candles(
                        key,
                        allow_expired=True,
                    )
                )
                if stale is not None:
                    logger.warning(
                        "TIMEOUT | %s | %s | "
                        "USING STALE CACHE",
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
                        "CONNECTION ERROR | "
                        "%s | %s | "
                        "USING STALE CACHE",
                        normalized_symbol,
                        normalized_timeframe,
                    )
                    return stale
                raise MarketDataError(
                    "Market API connection error: "
                    f"{exc}"
                ) from exc
            # =================================================
            # 8. TWELVE DATA JSON ERROR
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
                    # -------------------------------------------------
                    # DAILY LIMIT
                    # -------------------------------------------------
                    message_lower = str(
                        message
                    ).lower()
                    is_daily_limit = (
                        str(code) == "429"
                        or "run out of api credits"
                        in message_lower
                        or "daily" in message_lower
                        and "limit" in message_lower
                    )
                    if is_daily_limit:
                        await self._register_daily_limit()
                        stale = (
                            await self._get_cached_candles(
                                key,
                                allow_expired=True,
                            )
                        )
                        if stale is not None:
                            logger.warning(
                                "TWELVE DATA DAILY LIMIT | "
                                "%s | %s | "
                                "USING STALE CACHE",
                                normalized_symbol,
                                normalized_timeframe,
                            )
                            return stale
                        raise MarketDailyLimitError(
                            "Twelve Data daily limit: "
                            f"{message}"
                        )
                    # -------------------------------------------------
                    # NORMAL API ERROR
                    # -------------------------------------------------
                    stale = (
                        await self._get_cached_candles(
                            key,
                            allow_expired=True,
                        )
                    )
                    if stale is not None:
                        logger.warning(
                            "TWELVE DATA ERROR | "
                            "%s | %s | "
                            "USING STALE CACHE | "
                            "code=%s",
                            normalized_symbol,
                            normalized_timeframe,
                            code,
                        )
                        return stale
                    raise MarketDataError(
                        "Twelve Data error "
                        f"{code}: {message}"
                    )
            # =================================================
            # 9. PARSE
            # =================================================
            try:
                candles = self._parse_candles(
                    data
                )
            except MarketDataError:
                stale = (
                    await self._get_cached_candles(
                        key,
                        allow_expired=True,
                    )
                )
                if stale is not None:
                    logger.warning(
                        "PARSE ERROR | "
                        "%s | %s | "
                        "USING STALE CACHE",
                        normalized_symbol,
                        normalized_timeframe,
                    )
                    return stale
                raise
            # =================================================
            # 10. SAVE CACHE
            # =================================================
            ttl = self._get_cache_ttl(
                normalized_timeframe
            )
            await self._save_cached_candles(
                key,
                candles,
                ttl,
            )
            logger.debug(
                "CACHE UPDATED | "
                "%s | %s | "
                "candles=%s | ttl=%.1fs",
                normalized_symbol,
                normalized_timeframe,
                len(candles),
                ttl,
            )
            return list(candles)
    # =====================================================
    # MULTI TIMEFRAME
    # =====================================================
    async def get_multi_timeframe(
        self,
        symbol: str,
        timeframes: tuple[str, ...],
        limit: int = 200,
    ) -> dict[str, list[Candle]]:
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
    ) -> dict[str, list[Candle]]:
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
            if len(candles) >= 20:
                result[timeframe] = candles
        return result
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
        raw = data.get(
            "values"
        )
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
                timestamp = (
                    item.get(
                        "datetime"
                    )
                    or item.get(
                        "timestamp"
                    )
                    or item.get(
                        "time"
                    )
                )
                if timestamp is None:
                    continue
                timestamp = (
                    HTTPMarketProvider._parse_timestamp(
                        timestamp
                    )
                )
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
                volume_raw = item.get(
                    "volume",
                    0.0,
                )
                volume = (
                    0.0
                    if volume_raw
                    in (
                        None,
                        "",
                    )
                    else float(
                        volume_raw
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
                OverflowError,
            ):
                continue
            # =================================================
            # VALIDATION
            # =================================================
            if candle.high < candle.low:
                continue
            if (
                candle.open <= 0
                or candle.high <= 0
                or candle.low <= 0
                or candle.close <= 0
            ):
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
        # REMOVE DUPLICATES
        # =================================================
        unique: dict[
            datetime,
            Candle,
        ] = {}
        for candle in result:
            unique[
                candle.timestamp
            ] = candle
        result = list(
            unique.values()
        )
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
            numeric = float(
                value
            )
            if numeric > 10_000_000_000:
                numeric /= 1000.0
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
            try:
                numeric = float(
                    text
                )
            except ValueError as exc:
                raise ValueError(
                    f"Unsupported timestamp: {text}"
                ) from exc
            if numeric > 10_000_000_000:
                numeric /= 1000.0
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
    ) -> dict[str, list[Candle]]:
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
    ) -> dict[str, list[Candle]]:
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
            if len(candles) >= 20:
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
    "MarketDailyLimitError",
    "MarketProvider",
    "HTTPMarketProvider",
    "MarketClient",
]
