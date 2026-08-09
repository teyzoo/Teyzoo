from datetime import datetime

import aiohttp

from models import MarketCandle


class MarketDataError(Exception):
    pass


class MarketClient:

    def __init__(self):
        self.session: aiohttp.ClientSession | None = None

    async def start(self):
        if self.session is None:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(
                    total=10
                )
            )

    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None

    async def get_candles(
        self,
        symbol: str,
        limit: int = 100,
    ) -> list[MarketCandle]:

        """
        Временный источник.

        Здесь специально не притворяемся,
        что данные являются реальными котировками
        Pocket Option.

        Следующим этапом сюда подключается
        конкретный источник рыночных данных.
        """

        raise MarketDataError(
            "Источник рыночных данных ещё не подключён."
        )


market_client = MarketClient()
