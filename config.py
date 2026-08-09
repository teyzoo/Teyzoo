import os

from dotenv import load_dotenv


load_dotenv()


def get_int(name: str, default: int = 0) -> int:
    value = os.getenv(name)

    if value is None or value.strip() == "":
        return default

    try:
        return int(value)
    except ValueError:
        return default


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

ADMIN_ID = get_int("ADMIN_ID", 0)

HOST = os.getenv("HOST", "0.0.0.0")
PORT = get_int("PORT", 10000)

TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow")

SIGNAL_INTERVAL_MINUTES = get_int(
    "SIGNAL_INTERVAL_MINUTES",
    20,
)

MIN_SIGNAL_SCORE = get_int(
    "MIN_SIGNAL_SCORE",
    85,
)

DB_PATH = os.getenv(
    "DB_PATH",
    "bot.db",
)


if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN не установлен."
    )

if not ADMIN_ID:
    raise RuntimeError(
        "ADMIN_ID не установлен."
    )
