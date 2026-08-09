from __future__ import annotations
import os
def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Environment variable {name} is required."
        )
    return value
BOT_TOKEN = get_required_env("BOT_TOKEN")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./teyzus.db",
)
MARKET_API_URL = os.getenv(
    "MARKET_API_URL",
    "",
).strip()
MARKET_API_KEY = os.getenv(
    "MARKET_API_KEY",
    "",
).strip() or None
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
OWNER_ID = int(
    os.getenv(
        "OWNER_ID",
        "0",
    )
)
# Интервал между основными циклами.
SIGNAL_INTERVAL_MINUTES = int(
    os.getenv(
        "SIGNAL_INTERVAL_MINUTES",
        "20",
    )
)
# За сколько минут отправлять предупреждение.
PRE_SIGNAL_WARNING_MINUTES = int(
    os.getenv(
        "PRE_SIGNAL_WARNING_MINUTES",
        "2",
    )
)
# Минимальный аналитический score.
MIN_SIGNAL_SCORE = float(
    os.getenv(
        "MIN_SIGNAL_SCORE",
        "85",
    )
)
# Минимальная историческая вероятность.
MIN_HISTORICAL_PROBABILITY = float(
    os.getenv(
        "MIN_HISTORICAL_PROBABILITY",
        "70",
    )
)
LOG_LEVEL = os.getenv(
    "LOG_LEVEL",
    "INFO",
).upper()
