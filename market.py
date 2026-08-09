from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import aiohttp


logger = logging.getLogger(__name__)


class MarketDataError(Exception):
    """Ошибка получения рыночных данных."""


@dataclass(slots=True)
class Candle:
    """
    Одна свеча.

    timestamp:
        Время открытия свечи в UTC.

    open/high/low/close:
        OHLC значения.

    volume:
        Объём, если источник его предоставляет.
    """

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(slots=True)
class Quote:
    """
    Текущая котировка.
    """

    symbol: str
    bid: float
    ask: float
    timestamp: datetime

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread(self) -> float:
        return self.ask - self.bid


class MarketClient:
    """
    Единая точка доступа к рыночным данным.

    Остальной код бота не должен знать,
    откуда именно пришли котировки.

    Когда подключим конкретного поставщика,
    поменяется в основном этот слой.
    """

    def __init__(self) -> None:
        self.session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        if self.session is not None:
            return

        timeout = aiohttp.ClientTimeout(
            total=15,
            connect=5,
            sock_read=10,
        )

        self.session = aiohttp.ClientSession(
            timeout=timeout,
            headers={
                "User-Agent": (
                    "TEYZUS-Signal-Bot/1.0"
                )
            },
        )

        logger.info(
            "MarketClient started."
        )

    async def close(self) -> None:
        if self.session is None:
            return

        await self.session.close()
        self.session = None

        logger.info(
            "MarketClient closed."
        )

    def _ensure_session(self) -> aiohttp.ClientSession:
        if self.session is None:
            raise MarketDataError(
                "MarketClient ещё не запущен."
            )

        return self.session

    @staticmethod
    def normalize_symbol(
        symbol: str,
    ) -> str:
        """
        EUR/USD -> EURUSD

        EURUSD -> EURUSD
        eur/usd -> EURUSD
        """

        return (
            symbol
            .strip()
            .upper()
            .replace("/", "")
            .replace("-", "")
            .replace("_", "")
        )

    @staticmethod
    def utc_now() -> datetime:
        return datetime.now(timezone.utc)

    async def request_json(
        self,
        url: str,
        *,
        params: dict | None = None,
    ) -> dict | list:
        """
        Универсальный GET JSON.

        Добавлены:
        - timeout;
        - обработка HTTP ошибок;
        - обработка JSON ошибок;
        - повторные попытки.
        """

        session = self._ensure_session()

        last_error: Exception | None = None

        for attempt in range(3):

            try:

                async with session.get(
                    url,
                    params=params,
                ) as response:

                    if response.status == 429:
                        wait_time = 2 ** attempt

                        logger.warning(
                            "Rate limit. "
                            "Retry in %s sec.",
                            wait_time,
                        )

                        await asyncio.sleep(
                            wait_time
                        )

                        continue

                    if response.status >= 400:
                        body = await response.text()

                        raise MarketDataError(
                            f"HTTP {response.status}: "
                            f"{body[:300]}"
                        )

                    try:
                        return await response.json()

                    except Exception as exc:
                        raise MarketDataError(
                            "Источник вернул "
                            "некорректный JSON."
                        ) from exc

            except asyncio.CancelledError:
                raise

            except Exception as exc:

                last_error = exc

                logger.warning(
                    "Market request failed "
                    "(attempt %s/3): %s",
                    attempt + 1,
                    exc,
                )

                if attempt < 2:
                    await asyncio.sleep(
                        1 + attempt
                    )

        raise MarketDataError(
            "Не удалось получить рыночные данные."
        ) from last_error

    async def get_quote(
        self,
        symbol: str,
    ) -> Quote:
        """
        Получить текущую котировку.

        Реальный endpoint конкретного
        поставщика подключим следующим шагом.
        """

        normalized = self.normalize_symbol(
            symbol
        )

        raise MarketDataError(
            "Provider для котировок "
            f"{normalized} ещё не подключён."
        )

    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "1m",
        limit: int = 200,
    ) -> list[Candle]:
        """
        Получить исторические свечи.

        timeframe:
            1m
            5m
            15m
            30m
            1h
            и т.д.

        limit:
            Количество свечей.

        Пока конкретный provider
        не подключён, метод намеренно
        НЕ генерирует фальшивые данные.
        """

        if limit < 20:
            raise ValueError(
                "Для анализа нужно минимум "
                "20 свечей."
            )

        if limit > 5000:
            raise ValueError(
                "Слишком большое количество свечей."
            )

        normalized = self.normalize_symbol(
            symbol
        )

        raise MarketDataError(
            "Provider для исторических свечей "
            f"{normalized} ({timeframe}) "
            "ещё не подключён."
        )

    async def get_multi_timeframe(
        self,
        symbol: str,
        timeframes: tuple[str, ...] = (
            "1m",
            "5m",
            "15m",
        ),
        limit: int = 200,
    ) -> dict[str, list[Candle]]:
        """
        Получить несколько таймфреймов.

        Это понадобится для фильтрации:
        например, нельзя выдавать сигнал,
        если 1m показывает рост, а 15m
        находится в сильном нисходящем тренде.
        """

        result: dict[str, list[Candle]] = {}

        for timeframe in timeframes:

            candles = await self.get_candles(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
            )

            result[timeframe] = candles

        return result


market_client = MarketClient()
