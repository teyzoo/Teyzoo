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
    Важно:
    API key НЕ передаётся через Authorization Bearer.
    Он передаётся как:
        ?apikey=YOUR_KEY
    """
    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout: int = 15,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = (
            api_key.strip()
            if isinstance(api_key, str)
            else None
        )
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
        if not self.api_key:
            logger.warning(
                "MARKET_API_KEY is empty. "
                "Twelve Data requests will fail with HTTP 401."
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
    # NORMALIZE SYMBOL
    # -----------------------------------------------------
    @staticmethod
    def _normalize_symbol(
        symbol: str,
    ) -> str:
        symbol = str(symbol).strip().upper()
        if not symbol:
            raise ValueError(
                "Symbol is required."
            )
        # Twelve Data обычно принимает EUR/USD.
        #
        # Если где-то передали EURUSD,
        # автоматически превращаем в EUR/USD
        # для стандартных 6-символьных FX-пар.
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
    # -----------------------------------------------------
    # NORMALIZE TIMEFRAME
    # -----------------------------------------------------
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
        # Внутренние таймфреймы проекта
        # преобразуются в interval Twelve Data.
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
            # Дополнительные варианты.
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
    # -----------------------------------------------------
    # BUILD PARAMS
    # -----------------------------------------------------
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
        if limit < 20:
            raise ValueError(
                "At least 20 candles are required."
            )
        if limit > 5000:
            raise ValueError(
                "Maximum candle limit is 5000."
            )
        params = self._build_params(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
        )
        logger.debug(
            "Request candles: "
            "symbol=%s timeframe=%s limit=%s",
            params["symbol"],
            params["interval"],
            limit,
        )
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
                if response.status != 200:
                    raise MarketDataError(
                        "Market API returned HTTP "
                        f"{response.status}: "
                        f"{body[:1000]}"
                    )
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
            raise MarketDataError(
                "Market API timeout."
            ) from exc
        except aiohttp.ClientError as exc:
            raise MarketDataError(
                "Market API connection error: "
                f"{exc}"
            ) from exc
        # -------------------------------------------------
        # TWELVE DATA ERROR RESPONSE
        # -------------------------------------------------
        if isinstance(data, dict):
            status = str(
                data.get("status", "")
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
                raise MarketDataError(
                    "Twelve Data error "
                    f"{code}: {message}"
                )
        return self._parse_candles(
            data
        )
    # -----------------------------------------------------
    # PARSE CANDLES
    # -----------------------------------------------------
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
        # -------------------------------------------------
        # TWELVE DATA FORMAT
        #
        # {
        #   "meta": {...},
        #   "values": [
        #       {
        #           "datetime": "...",
        #           "open": "...",
        #           "high": "...",
        #           "low": "...",
        #           "close": "..."
        #       }
        #   ],
        #   "status": "ok"
        # }
        # -------------------------------------------------
        raw = data.get("values")
        # -------------------------------------------------
        # FALLBACK FORMATS
        # -------------------------------------------------
        if raw is None:
            raw = data.get("candles")
        if raw is None:
            raw = data.get("data")
        if raw is None:
            raw = data.get("results")
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
                # -----------------------------------------
                # TIMESTAMP
                # -----------------------------------------
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
                # -----------------------------------------
                # OHLC
                # -----------------------------------------
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
                # -----------------------------------------
                # VOLUME
                # -----------------------------------------
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
            result.append(
                candle
            )
        # -------------------------------------------------
        # SORT
        # -------------------------------------------------
        result.sort(
            key=lambda item: item.timestamp
        )
        # -------------------------------------------------
        # VALIDATION
        # -------------------------------------------------
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
        # datetime
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
        # Unix timestamp
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
        # -------------------------------------------------
        # ISO-8601
        # -------------------------------------------------
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
            # -------------------------------------------------
            # Twelve Data часто отдаёт:
            #
            # 2026-08-09 19:30:00
            #
            # datetime.fromisoformat() это понимает,
            # но если пришёл Unix timestamp строкой,
            # обработаем его здесь.
            # -------------------------------------------------
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
