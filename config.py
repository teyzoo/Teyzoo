from __future__ import annotations

import os


# ============================================================
# TELEGRAM
# ============================================================

BOT_TOKEN = os.getenv(
    "BOT_TOKEN",
    "",
).strip()


# ============================================================
# SERVER
# ============================================================

HOST = os.getenv(
    "HOST",
    "0.0.0.0",
).strip()


try:

    PORT = int(
        os.getenv(
            "PORT",
            "10000",
        )
    )

except ValueError:

    PORT = 10000


# ============================================================
# DATABASE
# ============================================================

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "",
).strip()


# ============================================================
# MARKET API
# ============================================================

MARKET_API_URL = os.getenv(
    "MARKET_API_URL",
    "",
).strip()


MARKET_API_KEY = os.getenv(
    "MARKET_API_KEY",
    "",
).strip()


# ============================================================
# ADMIN
# ============================================================

ADMIN_IDS_RAW = os.getenv(
    "ADMIN_IDS",
    "",
).strip()


def parse_admin_ids(
    value: str,
) -> list[int]:

    if not value:
        return []

    result: list[int] = []

    for item in value.split(","):

        item = item.strip()

        if not item:
            continue

        try:

            result.append(
                int(item)
            )

        except ValueError:

            continue

    return result


ADMIN_IDS = parse_admin_ids(
    ADMIN_IDS_RAW
)


# ============================================================
# TIMEZONE
# ============================================================

TIMEZONE = os.getenv(
    "TIMEZONE",
    "Europe/Moscow",
).strip()


# ============================================================
# SIGNAL SETTINGS
# ============================================================

MIN_SIGNAL_SCORE = float(
    os.getenv(
        "MIN_SIGNAL_SCORE",
        "85",
    )
)

MINIMUM_PROBABILITY = float(
    os.getenv(
        "MINIMUM_PROBABILITY",
        "70",
    )
)


# ============================================================
# RESULT CHECKER
# ============================================================

RESULT_CHECK_INTERVAL = int(
    os.getenv(
        "RESULT_CHECK_INTERVAL",
        "5",
    )
)


# ============================================================
# VALIDATION
# ============================================================

def validate_config():
    """
    Проверяет критические настройки.
    """

    errors: list[str] = []

    if not BOT_TOKEN:

        errors.append(
            "BOT_TOKEN не задан."
        )

    if not DATABASE_URL:

        errors.append(
            "DATABASE_URL не задан."
        )

    if not MARKET_API_URL:

        errors.append(
            "MARKET_API_URL не задан."
        )

    if errors:

        raise RuntimeError(
            "Ошибки конфигурации:\n"
            + "\n".join(
                f"- {error}"
                for error in errors
            )
        )
