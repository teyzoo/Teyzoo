from __future__ import annotations

import os

from dotenv import load_dotenv


load_dotenv()


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

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

ADMIN_IDS_RAW = os.getenv(
    "ADMIN_IDS",
    "",
).strip()


def parse_admin_ids() -> set[int]:
    result: set[int] = set()

    if not ADMIN_IDS_RAW:
        return result

    for value in ADMIN_IDS_RAW.split(","):
        value = value.strip()

        if not value:
            continue

        try:
            result.add(int(value))
        except ValueError:
            continue

    return result


ADMIN_IDS = parse_admin_ids()


if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN не установлен в Environment Variables."
    )
