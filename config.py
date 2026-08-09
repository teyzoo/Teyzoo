from __future__ import annotations

import os


def get_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)

    if value is None:
        return default

    value = value.strip()

    return value if value else default


BOT_TOKEN = get_env("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN не найден в Environment Variables."
    )


HOST = get_env(
    "HOST",
    "0.0.0.0",
) or "0.0.0.0"


PORT = int(
    get_env(
        "PORT",
        "10000",
    )
    or "10000"
)


DATABASE_URL = get_env(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./teyzus.db",
)


MARKET_API_URL = get_env(
    "MARKET_API_URL",
)


MARKET_API_KEY = get_env(
    "MARKET_API_KEY",
)


ADMIN_IDS_RAW = get_env(
    "ADMIN_IDS",
    "",
) or ""


ADMIN_IDS: set[int] = set()

for value in ADMIN_IDS_RAW.split(","):

    value = value.strip()

    if not value:
        continue

    try:
        ADMIN_IDS.add(int(value))
    except ValueError:
        continue


SIGNAL_INTERVAL_MINUTES = int(
    get_env(
        "SIGNAL_INTERVAL_MINUTES",
        "20",
    )
    or "20"
)


WARNING_MINUTES = int(
    get_env(
        "WARNING_MINUTES",
        "2",
    )
    or "2"
)


MIN_SIGNAL_SCORE = float(
    get_env(
        "MIN_SIGNAL_SCORE",
        "85",
    )
    or "85"
)


MIN_HISTORICAL_PROBABILITY = float(
    get_env(
        "MIN_HISTORICAL_PROBABILITY",
        "70",
    )
    or "70"
)


TIMEZONE = get_env(
    "TIMEZONE",
    "Europe/Moscow",
) or "Europe/Moscow"
