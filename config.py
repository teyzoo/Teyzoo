from __future__ import annotations

import os
from dataclasses import dataclass


def _get_int(
    name: str,
    default: int,
) -> int:
    value = os.getenv(name)

    if value is None:
        return default

    try:
        return int(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    bot_token: str
    database_url: str

    host: str
    port: int

    market_api_url: str
    market_api_key: str | None

    admin_ids: tuple[int, ...]

    signal_interval_minutes: int
    warning_minutes: int

    minimum_quality: float
    minimum_probability: float


def _parse_admin_ids() -> tuple[int, ...]:
    raw = os.getenv(
        "ADMIN_IDS",
        "",
    ).strip()

    if not raw:
        return ()

    result: list[int] = []

    for item in raw.split(","):

        item = item.strip()

        if not item:
            continue

        try:
            result.append(int(item))
        except ValueError:
            continue

    return tuple(result)


BOT_TOKEN = os.getenv(
    "BOT_TOKEN",
    "",
).strip()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./teyzus.db",
).strip()

HOST = os.getenv(
    "HOST",
    "0.0.0.0",
).strip()

PORT = _get_int(
    "PORT",
    10000,
)

MARKET_API_URL = os.getenv(
    "MARKET_API_URL",
    "",
).strip()

MARKET_API_KEY = os.getenv(
    "MARKET_API_KEY",
    "",
).strip() or None

ADMIN_IDS = _parse_admin_ids()

SIGNAL_INTERVAL_MINUTES = _get_int(
    "SIGNAL_INTERVAL_MINUTES",
    20,
)

WARNING_MINUTES = _get_int(
    "WARNING_MINUTES",
    2,
)

MINIMUM_QUALITY = float(
    os.getenv(
        "MINIMUM_QUALITY",
        "85",
    )
)

MINIMUM_PROBABILITY = float(
    os.getenv(
        "MINIMUM_PROBABILITY",
        "70",
    )
)


settings = Settings(
    bot_token=BOT_TOKEN,
    database_url=DATABASE_URL,
    host=HOST,
    port=PORT,
    market_api_url=MARKET_API_URL,
    market_api_key=MARKET_API_KEY,
    admin_ids=ADMIN_IDS,
    signal_interval_minutes=SIGNAL_INTERVAL_MINUTES,
    warning_minutes=WARNING_MINUTES,
    minimum_quality=MINIMUM_QUALITY,
    minimum_probability=MINIMUM_PROBABILITY,
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

    if settings.signal_interval_minutes <= 0:
        raise RuntimeError(
            "SIGNAL_INTERVAL_MINUTES должен "
            "быть больше 0."
        )

    if settings.warning_minutes < 0:
        raise RuntimeError(
            "WARNING_MINUTES не может быть "
            "отрицательным."
        )

    if not (
        0 <= settings.minimum_quality <= 100
    ):
        raise RuntimeError(
            "MINIMUM_QUALITY должен быть "
            "от 0 до 100."
        )

    if not (
        0 <= settings.minimum_probability <= 100
    ):
        raise RuntimeError(
            "MINIMUM_PROBABILITY должен быть "
            "от 0 до 100."
        )
