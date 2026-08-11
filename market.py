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

    - кэширование свечей;
    - разные TTL для разных таймфреймов;
    - deduplication одинаковых запросов;
    - локальный rate limiter;
    - дневной cooldown после исчерпания credits;
    - stale cache;
    - безопасный JSON parsing;
    - защита от повторного hammering API;
    - совместимость с MarketClient;
    - минимизация количества API-запросов.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout: int = 15,
        cache_ttl: float = 30.0,
        max_requests_per_minute: int = 6,
        daily_request_limit: int = 780,
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
            10.0,
            float(cache_ttl),
        )

        self.max_requests_per_minute = max(
            1,
            int(max_requests_per_minute),
        )

        # -------------------------------------------------
        # IMPORTANT
        # Не ставим ровно 800.
        # Оставляем небольшой запас.
        # -------------------------------------------------

        self.daily_request_limit = max(
            1,
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

        self._daily_reset_at: float = (
            time.time() + 86400
        )

        self._daily_limit_reached: bool = False

        # =================================================
        # HTTP
        # =================================================

        self.session: (
            aiohttp.ClientSession | None
        ) = None

        self._started = False

        # =================================================
        # STATS
        # =================================================

        self._stats = {
            "requests": 0,
            "cache_hits": 0,
            "stale_cache_hits": 0,
            "rate_limits": 0,
            "errors": 0,
        }

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

            self._daily_limit_reached = False

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
                60.0,
            )

        # -------------------------------------------------
        # 5 MINUTES
        # -------------------------------------------------

        if normalized == "5min":

            return max(
                self.cache_ttl,
                180.0,
            )

        # -------------------------------------------------
        # 15 MINUTES
        # -------------------------------------------------

        if normalized == "15min":

            return max(
                self.cache_ttl,
                300.0,
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
                600.0,
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
                900.0,
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
                1800.0,
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
            self._normalize_symbol(
                symbol
            ),
            self._normalize_timeframe(
                timeframe
            ),
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

            if allow_expired:

                self._stats[
                    "stale_cache_hits"
                ] += 1

            else:

                self._stats[
                    "cache_hits"
                ] += 1

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

                self._request_locks[
                    key
                ] = lock

            return lock

    # =====================================================
    # DAILY LIMIT RESET
    # =====================================================

    async def _reset_daily_counter_if_needed(
        self,
    ) -> None:

        now = time.time()

        if now >= self._daily_reset_at:

            self._daily_request_count = 0

            self._daily_limit_reached = False

            self._daily_reset_at = (
                now + 86400
            )

            logger.info(
                "Market daily request counter reset."
            )

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
            for timestamp
            in self._request_timestamps
            if timestamp > border
        ]

    # =====================================================
    # RATE LIMIT WAIT
    # =====================================================

    async def _wait_for_rate_limit_slot(
        self,
    ) -> None:

        while True:

            async with self._rate_limit_lock:

                await (
                    self._reset_daily_counter_if_needed()
                )

                # -----------------------------------------
                # DAILY LIMIT
                # -----------------------------------------

                if self._daily_limit_reached:

                    wait_for = max(
                        60.0,
                        self._daily_reset_at
                        - time.time(),
                    )

                    logger.warning(
                        "Daily market API limit "
                        "reached. Waiting %.0f seconds.",
                        wait_for,
                    )

                else:

                    now = time.monotonic()

                    # -------------------------------------
                    # GLOBAL COOLDOWN
                    # -------------------------------------

                    if (
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

                        # -----------------------------
                        # MINUTE LIMIT
                        # -----------------------------

                        if (
                            len(
                                self._request_timestamps
                            )
                            < self.max_requests_per_minute
                        ):

                            self._request_timestamps.append(
                                now
                            )

                            self._daily_request_count += 1

                            self._stats[
                                "requests"
                            ] += 1

                            return

                        oldest = min(
                            self._request_timestamps
                        )

                        wait_for = max(
                            0.5,
                            60.0
                            - (
                                now
                                - oldest
                            ),
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
    # REGISTER RATE LIMIT
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

            self._stats[
                "rate_limits"
            ] += 1

    # =====================================================
    # REGISTER DAILY LIMIT
    # =====================================================

    async def _register_daily_limit(
        self,
    ) -> None:

        async with self._rate_limit_lock:

            self._daily_limit_reached = True

            self._stats[
                "rate_limits"
            ] += 1

            logger.error(
                "Twelve Data daily API limit reached."
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
    # STALE CACHE HELPER
    # =====================================================

    async def _get_stale_cache(
        self,
        key: tuple[str, str, int],
        symbol: str,
        timeframe: str,
    ) -> list[Candle] | None:

        stale = await self._get_cached_candles(
            key,
            allow_expired=True,
        )

        if stale is not None:

            logger.warning(
                "USING STALE CACHE | %s | %s | candles=%s",
                symbol,
                timeframe,
                len(stale),
            )

            return stale

        return None

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

        cached = await self._get_cached_candles(
            key,
            allow_expired=False,
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
        # 2. DAILY LIMIT CHECK
        # =================================================

        async with self._rate_limit_lock:

            await (
                self._reset_daily_counter_if_needed()
            )

            daily_limit_reached = (
                self._daily_limit_reached
            )

        if daily_limit_reached:

            stale = await self._get_stale_cache(
                key,
                normalized_symbol,
                normalized_timeframe,
            )

            if stale is not None:
                return stale

            raise MarketRateLimitError(
                "Twelve Data daily request "
                "limit has been reached."
            )

        # =================================================
        # 3. REQUEST LOCK
        # =================================================

        request_lock = (
            await self._get_request_lock(
                key
            )
        )

        async with request_lock:

            # ---------------------------------------------
            # Recheck cache after lock.
            # ---------------------------------------------

            cached = (
                await self._get_cached_candles(
                    key,
                    allow_expired=False,
                )
            )

            if cached is not None:

                return cached

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

            await (
                self._wait_for_rate_limit_slot()
            )

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

                        await (
                            self._register_rate_limit(
                                60.0
                            )
                        )

                        # ---------------------------------
                        # Check daily limit wording.
                        # ---------------------------------

                        lower_body = body.lower()

                        if (
                            "credits"
                            in lower_body
                            or "daily"
                            in lower_body
                            or "limit being"
                            in lower_body
                            or "run out"
                            in lower_body
                        ):

                            await (
                                self._register_daily_limit()
                            )

                        stale = (
                            await self._get_stale_cache(
                                key,
                                normalized_symbol,
                                normalized_timeframe,
                            )
                        )

                        if stale is not None:

                            return stale

                        raise MarketRateLimitError(
                            "Market API returned HTTP 429: "
                            f"{body[:1000]}"
                        )

                    # =================================================
                    # OTHER HTTP ERRORS
                    # =================================================

                    if response.status != 200:

                        self._stats[
                            "errors"
                        ] += 1

                        stale = (
                            await self._get_stale_cache(
                                key,
                                normalized_symbol,
                                normalized_timeframe,
                            )
                        )

                        if stale is not None:
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

                        self._stats[
                            "errors"
                        ] += 1

                        stale = (
                            await self._get_stale_cache(
                                key,
                                normalized_symbol,
                                normalized_timeframe,
                            )
                        )

                        if stale is not None:
                            return stale

                        raise MarketDataError(
                            "Market API returned "
                            "invalid JSON."
                        ) from exc

            except asyncio.TimeoutError as exc:

                self._stats[
                    "errors"
                ] += 1

                stale = (
                    await self._get_stale_cache(
                        key,
                        normalized_symbol,
                        normalized_timeframe,
                    )
                )

                if stale is not None:
                    return stale

                raise MarketDataError(
                    "Market API timeout."
                ) from exc

            except aiohttp.ClientError as exc:

                self._stats[
                    "errors"
                ] += 1

                stale = (
                    await self._get_stale_cache(
                        key,
                        normalized_symbol,
                        normalized_timeframe,
                    )
                )

                if stale is not None:
                    return stale

                raise MarketDataError(
                    "Market API connection error: "
                    f"{exc}"
                ) from exc

            # =================================================
            # 6. TWELVE DATA JSON ERROR
            # =================================================

            if isinstance(
                data,
                dict,
            ):

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

                    message_text = str(
                        message
                    )

                    # -------------------------------------
                    # RATE LIMIT
                    # -------------------------------------

                    if str(code) == "429":

                        lower_message = (
                            message_text.lower()
                        )

                        await (
                            self._register_rate_limit(
                                60.0
                            )
                        )

                        if (
                            "credits"
                            in lower_message
                            or "daily"
                            in lower_message
                            or "run out"
                            in lower_message
                        ):

                            await (
                                self._register_daily_limit()
                            )

                        stale = (
                            await self._get_stale_cache(
                                key,
                                normalized_symbol,
                                normalized_timeframe,
                            )
                        )

                        if stale is not None:
                            return stale

                        raise MarketRateLimitError(
                            "Twelve Data rate limit: "
                            f"{message_text}"
                        )

                    # -------------------------------------
                    # OTHER API ERROR
                    # -------------------------------------

                    self._stats[
                        "errors"
                    ] += 1

                    stale = (
                        await self._get_stale_cache(
                            key,
                            normalized_symbol,
                            normalized_timeframe,
                        )
                    )

                    if stale is not None:
                        return stale

                    raise MarketDataError(
                        "Twelve Data error "
                        f"{code}: {message_text}"
                    )

            # =================================================
            # 7. PARSE
            # =================================================

            candles = self._parse_candles(
                data
            )

            # =================================================
            # 8. SAVE CACHE
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

            try:

                result[timeframe] = (
                    await self.get_candles(
                        symbol=symbol,
                        timeframe=timeframe,
                        limit=limit,
                    )
                )

            except MarketRateLimitError:

                logger.warning(
                    "Rate limit while loading "
                    "%s %s.",
                    symbol,
                    timeframe,
                )

                break

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

            except MarketRateLimitError as exc:

                logger.warning(
                    "Market rate limit reached "
                    "for %s %s: %s",
                    symbol,
                    timeframe,
                    exc,
                )

                # Не продолжаем бессмысленно
                # делать новые запросы.

                break

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

    # =====================================================
    # STATS
    # =====================================================

    async def get_stats(
        self,
    ) -> dict[str, Any]:

        async with self._rate_limit_lock:

            await (
                self._reset_daily_counter_if_needed()
            )

            daily_remaining = max(
                0,
                self.daily_request_limit
                - self._daily_request_count,
            )

            return {
                "started": self._started,
                "daily_requests": (
                    self._daily_request_count
                ),
                "daily_remaining_local": (
                    daily_remaining
                ),
                "daily_limit_reached": (
                    self._daily_limit_reached
                ),
                "rate_limited_until": (
                    self._rate_limited_until
                ),
                "cache_size": len(
                    self._cache
                ),
                **self._stats,
            }


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

            try:

                result[timeframe] = (
                    await self.get_candles(
                        symbol=symbol,
                        timeframe=timeframe,
                        limit=limit,
                    )
                )

            except MarketRateLimitError:

                logger.warning(
                    "Stopping multi-timeframe "
                    "request because market "
                    "rate limit was reached."
                )

                break

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

            except MarketRateLimitError as exc:

                logger.warning(
                    "Market rate limit reached "
                    "while loading %s %s: %s",
                    symbol,
                    timeframe,
                    exc,
                )

                break

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
    # STATS
    # =====================================================

    async def get_stats(
        self,
    ) -> dict[str, Any]:

        provider = self.provider

        get_stats = getattr(
            provider,
            "get_stats",
            None,
        )

        if get_stats is None:

            return {}

        return await get_stats()


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
