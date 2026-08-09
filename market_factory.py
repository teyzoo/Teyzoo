from __future__ import annotations

from config import (
    MARKET_API_KEY,
    MARKET_API_URL,
)

from market import (
    HTTPMarketProvider,
    MarketClient,
)


def create_market_client() -> MarketClient:

    if not MARKET_API_URL:
        raise RuntimeError(
            "MARKET_API_URL не задан "
            "в переменных окружения."
        )

    provider = HTTPMarketProvider(
        base_url=MARKET_API_URL,
        api_key=MARKET_API_KEY,
    )

    return MarketClient(
        provider=provider
    )
