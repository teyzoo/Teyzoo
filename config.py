# config.py

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


def get_required_env(
    name: str,
) -> str:
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
        return int(
            value
            if value is not None
            else default
        )
    except ValueError as exc:
        raise RuntimeError(
            f"Environment variable {name} "
            f"must be an integer."
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
        return float(
            value
            if value is not None
            else default
        )
    except ValueError as exc:
        raise RuntimeError(
            f"Environment variable {name} "
            f"must be a number."
        ) from exc


# =========================================================
# TELEGRAM
# =========================================================

BOT_TOKEN: Final[str] = get_required_env(
    "BOT_TOKEN"
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

    # Owner автоматически получает
    # права администратора.
    if OWNER_ID > 0:
        result.add(OWNER_ID)

    for value in ADMIN_IDS_RAW.split(","):
        value = value.strip()

        if not value:
            continue

        try:
            result.add(
                int(value)
            )
        except ValueError:
            continue

    return result


ADMIN_IDS: Final[set[int]] = (
    get_admin_ids()
)


# =========================================================
# DATABASE
# =========================================================

DATABASE_URL: Final[str] = (
    get_required_env(
        "DATABASE_URL"
    )
)


# =========================================================
# MARKET API
# =========================================================

MARKET_API_URL: Final[str] = (
    get_required_env(
        "MARKET_API_URL"
    )
)


MARKET_API_KEY: Final[str | None] = (
    get_env(
        "MARKET_API_KEY"
    )
)


# =========================================================
# SERVER
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
# SIGNAL SETTINGS
# =========================================================

# Минимальный Quality Score,
# при котором сигнал вообще может
# пройти фильтр.
SIGNAL_MINIMUM_QUALITY: Final[float] = (
    get_float_env(
        "SIGNAL_MINIMUM_QUALITY",
        85.0,
    )
)


# Минимальная историческая вероятность.
SIGNAL_MINIMUM_PROBABILITY: Final[float] = (
    get_float_env(
        "SIGNAL_MINIMUM_PROBABILITY",
        70.0,
    )
)


# За сколько минут до сигнала
# отправляется предупреждение.
SIGNAL_WARNING_MINUTES: Final[int] = (
    get_int_env(
        "SIGNAL_WARNING_MINUTES",
        2,
    )
)


# Длительность сигнала.
SIGNAL_EXPIRY_MINUTES: Final[int] = (
    get_int_env(
        "SIGNAL_EXPIRY_MINUTES",
        20,
    )
)


# Интервал основного анализа.
SIGNAL_ANALYSIS_INTERVAL: Final[int] = (
    get_int_env(
        "SIGNAL_ANALYSIS_INTERVAL",
        20,
    )
)


# =========================================================
# MARKET SETTINGS
# =========================================================

MARKET_REQUEST_TIMEOUT: Final[int] = (
    get_int_env(
        "MARKET_REQUEST_TIMEOUT",
        15,
    )
)


MARKET_CANDLE_LIMIT: Final[int] = (
    get_int_env(
        "MARKET_CANDLE_LIMIT",
        200,
    )
)


# Минимум свечей,
# необходимых для анализа.
MARKET_MIN_CANDLES: Final[int] = (
    get_int_env(
        "MARKET_MIN_CANDLES",
        50,
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
# DEFAULT FOREX PAIRS
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
# DATABASE / TRACKER SETTINGS
# =========================================================

RESULT_CHECK_INTERVAL: Final[int] = (
    get_int_env(
        "RESULT_CHECK_INTERVAL",
        30,
    )
)


WARNING_CHECK_INTERVAL: Final[int] = (
    get_int_env(
        "WARNING_CHECK_INTERVAL",
        15,
    )
)


# =========================================================
# PROBABILITY CALIBRATION
# =========================================================

PROBABILITY_MINIMUM_SAMPLES: Final[int] = (
    get_int_env(
        "PROBABILITY_MINIMUM_SAMPLES",
        100,
    )
)


# =========================================================
# APPLICATION SETTINGS
# =========================================================

MAX_APPLICATION_LENGTH: Final[int] = (
    get_int_env(
        "MAX_APPLICATION_LENGTH",
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
).upper()


# =========================================================
# CONFIG VALIDATION
# =========================================================

def validate_config() -> None:
    """
    Проверяет основные настройки приложения
    перед запуском.
    """

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

    if PORT <= 0 or PORT > 65535:
        raise RuntimeError(
            "PORT must be between 1 and 65535."
        )

    if (
        SIGNAL_MINIMUM_QUALITY < 0
        or SIGNAL_MINIMUM_QUALITY > 100
    ):
        raise RuntimeError(
            "SIGNAL_MINIMUM_QUALITY must be "
            "between 0 and 100."
        )

    if (
        SIGNAL_MINIMUM_PROBABILITY < 0
        or SIGNAL_MINIMUM_PROBABILITY > 100
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
            "SIGNAL_ANALYSIS_INTERVAL must be "
            "greater than 0."
        )

    if MARKET_REQUEST_TIMEOUT <= 0:
        raise RuntimeError(
            "MARKET_REQUEST_TIMEOUT must be "
            "greater than 0."
        )

    if MARKET_CANDLE_LIMIT < 20:
        raise RuntimeError(
            "MARKET_CANDLE_LIMIT must be "
            "at least 20."
        )

    if MARKET_CANDLE_LIMIT > 5000:
        raise RuntimeError(
            "MARKET_CANDLE_LIMIT cannot exceed 5000."
        )

    if MARKET_MIN_CANDLES < 20:
        raise RuntimeError(
            "MARKET_MIN_CANDLES must be "
            "at least 20."
        )

    if not TIMEFRAMES:
        raise RuntimeError(
            "TIMEFRAMES cannot be empty."
        )

    if not DEFAULT_PAIRS:
        raise RuntimeError(
            "DEFAULT_PAIRS cannot be empty."
        )

    if RESULT_CHECK_INTERVAL <= 0:
        raise RuntimeError(
            "RESULT_CHECK_INTERVAL must be "
            "greater than 0."
        )

    if WARNING_CHECK_INTERVAL <= 0:
        raise RuntimeError(
            "WARNING_CHECK_INTERVAL must be "
            "greater than 0."
        )

    if PROBABILITY_MINIMUM_SAMPLES <= 0:
        raise RuntimeError(
            "PROBABILITY_MINIMUM_SAMPLES must be "
            "greater than 0."
        )

    if MAX_APPLICATION_LENGTH <= 0:
        raise RuntimeError(
            "MAX_APPLICATION_LENGTH must be "
            "greater than 0."
        )


__all__ = [
    "BOT_TOKEN",
    "OWNER_ID",
    "ADMIN_IDS",
    "DATABASE_URL",
    "MARKET_API_URL",
    "MARKET_API_KEY",
    "HOST",
    "PORT",
    "SIGNAL_MINIMUM_QUALITY",
    "SIGNAL_MINIMUM_PROBABILITY",
    "SIGNAL_WARNING_MINUTES",
    "SIGNAL_EXPIRY_MINUTES",
    "SIGNAL_ANALYSIS_INTERVAL",
    "MARKET_REQUEST_TIMEOUT",
    "MARKET_CANDLE_LIMIT",
    "MARKET_MIN_CANDLES",
    "TIMEFRAMES",
    "DEFAULT_PAIRS",
    "RESULT_CHECK_INTERVAL",
    "WARNING_CHECK_INTERVAL",
    "PROBABILITY_MINIMUM_SAMPLES",
    "MAX_APPLICATION_LENGTH",
    "LOG_LEVEL",
    "validate_config",
]
