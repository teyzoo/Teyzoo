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
    """
    Создаёт HTTP-провайдер рыночных данных.

    Все настройки берутся из config.py.
    """

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
    """
    Создаёт MarketClient с HTTP-провайдером.
    """

    provider = create_market_provider()

    client = MarketClient(
        provider=provider,
    )

    logger.info(
        "Market client created."
    )

    return client
