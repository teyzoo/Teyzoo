from __future__ import annotations
import os
from typing import Final
# =========================================================
# ENV HELPERS
# =========================================================
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
def get_required_env(name: str) -> str:
    value = get_env(name)
    if not value:
        raise RuntimeError(
            f"Environment variable {name} is required."
        )
    return value
def get_int_env(
    name: str,
    default: int,
) -> int:
    value = get_env(
        name,
        str(default),
    )
    try:
        return int(value or default)
    except ValueError as exc:
        raise RuntimeError(
            f"Environment variable {name} must be an integer."
        ) from exc
def get_float_env(
    name: str,
    default: float,
) -> float:
    value = get_env(
        name,
        str(default),
    )
    try:
        return float(value or default)
    except ValueError as exc:
        raise RuntimeError(
            f"Environment variable {name} must be a number."
        ) from exc
def get_bool_env(
    name: str,
    default: bool,
) -> bool:
    value = get_env(
        name,
        None,
    )
    if value is None:
        return default
    value = value.lower().strip()
    if value in {
        "1",
        "true",
        "yes",
        "on",
        "y",
    }:
        return True
    if value in {
        "0",
        "false",
        "no",
        "off",
        "n",
    }:
        return False
    raise RuntimeError(
        f"Environment variable {name} must be "
        f"a boolean: true/false."
    )
# =========================================================
# TELEGRAM
# =========================================================
BOT_TOKEN: Final[str] = get_required_env(
    "BOT_TOKEN"
)
# =========================================================
# DATABASE
# =========================================================
DATABASE_URL: Final[str] = get_required_env(
    "DATABASE_URL"
)
# =========================================================
# OWNER / ADMINS
# =========================================================
OWNER_ID: Final[int] = get_int_env(
    "OWNER_ID",
    0,
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
    # OWNER автоматически считается администратором.
    if OWNER_ID > 0:
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
def is_admin(
    telegram_id: int,
) -> bool:
    return telegram_id in ADMIN_IDS
def is_owner(
    telegram_id: int,
) -> bool:
    return (
        OWNER_ID > 0
        and telegram_id == OWNER_ID
    )
# =========================================================
# FASTAPI / RENDER
# =========================================================
HOST: Final[str] = (
    get_env(
        "HOST",
        "0.0.0.0",
    )
    or "0.0.0.0"
)
PORT: Final[int] = get_int_env(
    "PORT",
    10000,
)
# =========================================================
# MARKET API
# =========================================================
MARKET_API_URL: Final[str] = get_required_env(
    "MARKET_API_URL"
)
MARKET_API_KEY: Final[str | None] = get_env(
    "MARKET_API_KEY"
)
MARKET_REQUEST_TIMEOUT: Final[int] = get_int_env(
    "MARKET_REQUEST_TIMEOUT",
    15,
)
MARKET_CANDLE_LIMIT: Final[int] = get_int_env(
    "MARKET_CANDLE_LIMIT",
    200,
)
# =========================================================
# SIGNAL SETTINGS
# =========================================================
# Минимальное качество сигнала.
#
# Можно НЕ указывать SIGNAL_MINIMUM_QUALITY
# в Render. В таком случае используется 85%.
SIGNAL_MINIMUM_QUALITY: Final[float] = (
    get_float_env(
        "SIGNAL_MINIMUM_QUALITY",
        85.0,
    )
)
# Минимальная историческая вероятность.
#
# Можно НЕ указывать SIGNAL_MINIMUM_PROBABILITY
# в Render. В таком случае используется 70%.
SIGNAL_MINIMUM_PROBABILITY: Final[float] = (
    get_float_env(
        "SIGNAL_MINIMUM_PROBABILITY",
        70.0,
    )
)
# =========================================================
# SIGNAL POLICY COMPATIBILITY
# =========================================================
#
# Этот параметр требуется signal_policy.py.
#
# Его НЕ обязательно добавлять в Render.
#
# По умолчанию историческая вероятность учитывается
# при фильтрации сигнала.
#
# Если в будущем понадобится отключить этот фильтр,
# можно добавить в Render:
#
# SIGNAL_REQUIRE_HISTORICAL_PROBABILITY=false
#
# Но сейчас этого делать не нужно.
#
SIGNAL_REQUIRE_HISTORICAL_PROBABILITY: Final[bool] = (
    get_bool_env(
        "SIGNAL_REQUIRE_HISTORICAL_PROBABILITY",
        True,
    )
)
# =========================================================
# SIGNAL TIMING
# =========================================================
SIGNAL_WARNING_MINUTES: Final[int] = (
    get_int_env(
        "SIGNAL_WARNING_MINUTES",
        2,
    )
)
SIGNAL_EXPIRY_MINUTES: Final[int] = (
    get_int_env(
        "SIGNAL_EXPIRY_MINUTES",
        20,
    )
)
# =========================================================
# SCHEDULER
# =========================================================
SIGNAL_ANALYSIS_INTERVAL: Final[int] = (
    get_int_env(
        "SIGNAL_ANALYSIS_INTERVAL",
        20,
    )
)
SIGNAL_WARNING_INTERVAL: Final[int] = (
    get_int_env(
        "SIGNAL_WARNING_INTERVAL",
        15,
    )
)
SIGNAL_RESULT_INTERVAL: Final[int] = (
    get_int_env(
        "SIGNAL_RESULT_INTERVAL",
        30,
    )
)
# =========================================================
# TIMEFRAMES
# =========================================================
TIMEFRAMES: Final[tuple[str, ...]] = (
    "1m",
    "5m",
    "15m",
)
# =========================================================
# DEFAULT MARKET PAIRS
# =========================================================
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
# =========================================================
# APPLICATION SETTINGS
# =========================================================
APPLICATION_MAX_LENGTH: Final[int] = (
    get_int_env(
        "APPLICATION_MAX_LENGTH",
        4000,
    )
)
# =========================================================
# LOGGING
# =========================================================
LOG_LEVEL: Final[str] = (
    get_env(
        "LOG_LEVEL",
        "INFO",
    )
    or "INFO"
)
# =========================================================
# VALIDATION
# =========================================================
def validate_config() -> None:
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN is not configured."
        )
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not configured."
        )
    if not MARKET_API_URL:
        raise RuntimeError(
            "MARKET_API_URL is not configured."
        )
    if OWNER_ID <= 0:
        raise RuntimeError(
            "OWNER_ID must be configured "
            "with a valid Telegram user ID."
        )
    if PORT <= 0 or PORT > 65535:
        raise RuntimeError(
            "PORT must be between 1 and 65535."
        )
    if MARKET_REQUEST_TIMEOUT <= 0:
        raise RuntimeError(
            "MARKET_REQUEST_TIMEOUT must be greater than 0."
        )
    if MARKET_CANDLE_LIMIT < 20:
        raise RuntimeError(
            "MARKET_CANDLE_LIMIT must be at least 20."
        )
    if MARKET_CANDLE_LIMIT > 5000:
        raise RuntimeError(
            "MARKET_CANDLE_LIMIT cannot exceed 5000."
        )
    if not (
        0 <= SIGNAL_MINIMUM_QUALITY <= 100
    ):
        raise RuntimeError(
            "SIGNAL_MINIMUM_QUALITY must be "
            "between 0 and 100."
        )
    if not (
        0 <= SIGNAL_MINIMUM_PROBABILITY <= 100
    ):
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
    if SIGNAL_ANALYSIS_INTERVAL <= 0:
        raise RuntimeError(
            "SIGNAL_ANALYSIS_INTERVAL must be greater than 0."
        )
    if SIGNAL_WARNING_INTERVAL <= 0:
        raise RuntimeError(
            "SIGNAL_WARNING_INTERVAL must be greater than 0."
        )
    if SIGNAL_RESULT_INTERVAL <= 0:
        raise RuntimeError(
            "SIGNAL_RESULT_INTERVAL must be greater than 0."
        )
    if APPLICATION_MAX_LENGTH <= 0:
        raise RuntimeError(
            "APPLICATION_MAX_LENGTH must be greater than 0."
        )
# =========================================================
# STARTUP VALIDATION
# =========================================================
validate_config()
