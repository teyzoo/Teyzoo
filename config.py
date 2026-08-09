from __future__ import annotations

import os


def _required(name: str) -> str:

    value = os.getenv(name)

    if not value:
        raise RuntimeError(
            f"Не задана переменная окружения: {name}"
        )

    return value


BOT_TOKEN = _required(
    "BOT_TOKEN"
)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./teyzus.db",
)

MARKET_API_URL = os.getenv(
    "MARKET_API_URL",
    "",
)

MARKET_API_KEY = os.getenv(
    "MARKET_API_KEY",
)

ADMIN_IDS = {
    int(value.strip())
    for value in os.getenv(
        "ADMIN_IDS",
        "",
    ).split(",")
    if value.strip().isdigit()
}

HOST = os.getenv(
    "HOST",
    "0.0.0.0",
)

PORT = int(
    os.getenv(
        "PORT",
        "10000",
    )
)

SIGNAL_INTERVAL_MINUTES = 20

WARNING_MINUTES = 2

MIN_SIGNAL_SCORE = float(
    os.getenv(
        "MIN_SIGNAL_SCORE",
        "85",
    )
)

MIN_HISTORICAL_PROBABILITY = float(
    os.getenv(
        "MIN_HISTORICAL_PROBABILITY",
        "70",
    )
)

MIN_PROBABILITY_SAMPLES = int(
    os.getenv(
        "MIN_PROBABILITY_SAMPLES",
        "100",
    )
)

TIMEZONE = "Europe/Moscow"
