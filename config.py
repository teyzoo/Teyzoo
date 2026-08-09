from __future__ import annotations

import os

from dotenv import load_dotenv


load_dotenv()


BOT_TOKEN = os.getenv(
    "BOT_TOKEN",
    "",
).strip()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "",
).strip()

MARKET_API_URL = os.getenv(
    "MARKET_API_URL",
    "",
).strip()

MARKET_API_KEY = os.getenv(
    "MARKET_API_KEY",
    "",
).strip()

HOST = os.getenv(
    "HOST",
    "0.0.0.0",
).strip()

PORT = int(
    os.getenv(
        "PORT",
        "10000",
    )
)

OWNER_ID = int(
    os.getenv(
        "OWNER_ID",
        "0",
    )
)

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


def validate_config() -> None:

    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN не установлен."
        )

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL не установлен."
        )

    if OWNER_ID <= 0:
        raise RuntimeError(
            "OWNER_ID не установлен."
        )
