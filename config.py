from __future__ import annotations

import os

from dotenv import load_dotenv


load_dotenv()


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./teyzus.db",
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

ADMIN_IDS = {
    int(value.strip())
    for value in os.getenv(
        "ADMIN_IDS",
        "",
    ).split(",")
    if value.strip().isdigit()
}


if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN не задан в Environment Variables."
    )
