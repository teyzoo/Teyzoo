from __future__ import annotations

import os
from typing import Final


def get_env(
    name: str,
    default: str | None = None,
) -> str | None:
    value = os.getenv(name)

    if value is None:
        return default

    value = value.strip()

    if not value:
        return default

    return value


def get_required_env(
    name: str,
) -> str:
    value = get_env(name)

    if not value:
        raise RuntimeError(
            f"Environment variable {name} is required."
        )

    return value


# ---------------------------------------------------------
# TELEGRAM
# ---------------------------------------------------------

BOT_TOKEN: Final[str] = get_required_env(
    "BOT_TOKEN"
)


# ---------------------------------------------------------
# OWNER / ADMINS
# ---------------------------------------------------------

OWNER_ID: Final[int] = int(
    get_required_env("OWNER_ID")
)


ADMIN_IDS_RAW: Final[str] = (
    get_env(
        "ADMIN_IDS",
        "",
    )
    or ""
)


def get_admin_ids() -> set[int]:
    result: set[int] = set()

    # Владелец автоматически является администратором.
    result.add(OWNER_ID)

    for value in ADMIN_IDS_RAW.split(","):
        value = value.strip()

        if not value:
            continue

        try:
            result.add(int(value))
        except ValueError:
            continue

    return result


ADMIN_IDS: Final[set[int]] = get_admin_ids()


# ---------------------------------------------------------
# DATABASE
# ---------------------------------------------------------

DATABASE_URL: Final[str] = get_required_env(
    "DATABASE_URL"
)


# ---------------------------------------------------------
# MARKET API
# ---------------------------------------------------------

MARKET_API_URL: Final[str] = get_required_env(
    "MARKET_API_URL"
)


MARKET_API_KEY: Final[str | None] = get_env(
    "MARKET_API_KEY"
)


# ---------------------------------------------------------
# WEB SERVER
# ---------------------------------------------------------

HOST: Final[str] = (
    get_env(
        "HOST",
        "0.0.0.0",
    )
    or "0.0.0.0"
)


PORT: Final[int] = int(
    get_env(
        "PORT",
        "10000",
    )
    or "10000"
)


# ---------------------------------------------------------
# SIGNAL SETTINGS
# ---------------------------------------------------------

SIGNAL_MINIMUM_QUALITY: Final[float] = float(
    get_env(
        "SIGNAL_MINIMUM_QUALITY",
        "85",
    )
    or "85"
)


SIGNAL_MINIMUM_PROBABILITY: Final[float] = float(
    get_env(
        "SIGNAL_MINIMUM_PROBABILITY",
        "70",
    )
    or "70"
)


SIGNAL_WARNING_MINUTES: Final[int] = int(
    get_env(
        "SIGNAL_WARNING_MINUTES",
        "2",
    )
    or "2"
)


SIGNAL_EXPIRY_MINUTES: Final[int] = int(
    get_env(
        "SIGNAL_EXPIRY_MINUTES",
        "20",
    )
    or "20"
)


# ---------------------------------------------------------
# MARKET SETTINGS
# ---------------------------------------------------------

MARKET_REQUEST_TIMEOUT: Final[int] = int(
    get_env(
        "MARKET_REQUEST_TIMEOUT",
        "15",
    )
    or "15"
)


MARKET_CANDLE_LIMIT: Final[int] = int(
    get_env(
        "MARKET_CANDLE_LIMIT",
        "200",
    )
    or "200"
)


# ---------------------------------------------------------
# TIMEFRAMES
# ---------------------------------------------------------

TIMEFRAMES: Final[tuple[str, ...]] = (
    "1m",
    "5m",
    "15m",
)


# ---------------------------------------------------------
# DEFAULT PAIRS
# ---------------------------------------------------------

DEFAULT_PAIRS: Final[list[str]] = [
    "EUR/USD",
    "GBP/USD",
    "USD/JPY",
    "USD/CHF",
    "AUD/USD",
    "USD/CAD",
    "NZD/USD",
    "EUR/GBP",
    "EUR/JPY",
    "GBP/JPY",
]


# ---------------------------------------------------------
# CONFIG VALIDATION
# ---------------------------------------------------------

def validate_config() -> None:

    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN is not configured."
        )

    if OWNER_ID <= 0:
        raise RuntimeError(
            "OWNER_ID must be a positive Telegram user ID."
        )

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not configured."
        )

    if not MARKET_API_URL:
        raise RuntimeError(
            "MARKET_API_URL is not configured."
        )

    if PORT <= 0 or PORT > 65535:
        raise RuntimeError(
            "PORT must be between 1 and 65535."
        )

    if not 0 <= SIGNAL_MINIMUM_QUALITY <= 100:
        raise RuntimeError(
            "SIGNAL_MINIMUM_QUALITY must be "
            "between 0 and 100."
        )

    if not 0 <= SIGNAL_MINIMUM_PROBABILITY <= 100:
        raise RuntimeError(
            "SIGNAL_MINIMUM_PROBABILITY must be "
            "between 0 and 100."
        )

    if SIGNAL_WARNING_MINUTES < 0:
        raise RuntimeError(
            "SIGNAL_WARNING_MINUTES cannot be negative."
        )

    if SIGNAL_EXPIRY_MINUTES <= 0:
        raise RuntimeError(
            "SIGNAL_EXPIRY_MINUTES must be greater than 0."
        )

    if MARKET_REQUEST_TIMEOUT <= 0:
        raise RuntimeError(
            "MARKET_REQUEST_TIMEOUT must be greater than 0."
        )

    if MARKET_CANDLE_LIMIT <= 0:
        raise RuntimeError(
            "MARKET_CANDLE_LIMIT must be greater than 0."
        )

    if not TIMEFRAMES:
        raise RuntimeError(
            "TIMEFRAMES cannot be empty."
        )

    if not DEFAULT_PAIRS:
        raise RuntimeError(
            "DEFAULT_PAIRS cannot be empty."
        )
