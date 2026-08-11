from __future__ import annotations

import logging

from config import (
    MARKET_API_KEY,
    MARKET_API_URL,
)

from market import (
    HTTPMarketProvider,
    MarketClient,
    MarketProvider,
)


logger = logging.getLogger(
    "market_factory"
)


def create_market_provider() -> MarketProvider:
    if not MARKET_API_URL:
        raise RuntimeError(
            "MARKET_API_URL не задан."
        )

    logger.info(
        "Creating HTTP market provider: %s",
        MARKET_API_URL,
    )

    return HTTPMarketProvider(
        base_url=MARKET_API_URL,
        api_key=MARKET_API_KEY,
    )


def create_market_client() -> MarketClient:
    provider = create_market_provider()

    client = MarketClient(
        provider=provider,
    )

    logger.info(
        "Market client created."
    )

    return client


__all__ = [
    "create_market_provider",
    "create_market_client",
]
