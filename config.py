from __future__ import annotations
import os
def _get_env(
    name: str,
    default: str | None = None,
) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value or default
BOT_TOKEN = _get_env(
    "BOT_TOKEN"
)
HOST = _get_env(
    "HOST",
    "0.0.0.0",
)
PORT = int(
    _get_env(
        "PORT",
        "10000",
    )
)
DATABASE_URL = _get_env(
    "DATABASE_URL",
)
MARKET_API_URL = _get_env(
    "MARKET_API_URL",
)
MARKET_API_KEY = _get_env(
    "MARKET_API_KEY"
)
ADMIN_IDS_RAW = _get_env(
    "ADMIN_IDS",
    "",
)
def get_admin_ids() -> set[int]:
    result: set[int] = set()
    for value in ADMIN_IDS_RAW.split(","):
        value = value.strip()
        if not value:
            continue
        try:
            result.add(int(value))
        except ValueError:
            continue
    return result
ADMIN_IDS = get_admin_ids()
def validate_config() -> None:
    missing: list[str] = []
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if not DATABASE_URL:
        missing.append("DATABASE_URL")
    if not MARKET_API_URL:
        missing.append("MARKET_API_URL")
    if missing:
        raise RuntimeError(
            "Missing required environment variables: "
            + ", ".join(missing)
        )
