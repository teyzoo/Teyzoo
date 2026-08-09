from __future__ import annotations

from market import (
    HTTPMarketProvider,
    MarketClient,
)

from config import (
    MARKET_API_KEY,
    MARKET_API_URL,
)


def create_market_client() -> MarketClient:

    if not MARKET_API_URL:

        raise RuntimeError(
            "MARKET_API_URL не задан."
        )

    provider = HTTPMarketProvider(
        base_url=MARKET_API_URL,
        api_key=MARKET_API_KEY,
    )

    return MarketClient(
        provider=provider
    )
