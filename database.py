from __future__ import annotations
import logging
import os
from datetime import datetime
from typing import Any
import aiosqlite
logger = logging.getLogger("database")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "teyzus.db",
)
def _database_path() -> str:
    """
    Для текущей версии используем SQLite.
    Если DATABASE_URL начинается с sqlite://,
    преобразуем его в обычный путь.
    Примеры:
        DATABASE_URL=teyzus.db
        DATABASE_URL=sqlite:///teyzus.db
    """
    value = DATABASE_URL.strip()
    if value.startswith("sqlite:///"):
        return value.replace(
            "sqlite:///",
            "",
            1,
        )
    if value.startswith("sqlite://"):
        return value.replace(
            "sqlite://",
            "",
            1,
        )
    return value
DB_PATH = _database_path()
async def init_db() -> None:
    async with aiosqlite.connect(
        DB_PATH
    ) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                is_admin INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                score REAL NOT NULL DEFAULT 0,
                historical_probability REAL,
                entry_price REAL,
                exit_price REAL,
                created_at TEXT NOT NULL,
                close_time TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'CREATED',
                warning_sent INTEGER NOT NULL DEFAULT 0,
                result_checked INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        await db.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_signals_close_time
            ON signals(close_time)
            """
        )
        await db.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_signals_status
            ON signals(status)
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS signal_statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id INTEGER NOT NULL,
                result TEXT NOT NULL,
                entry_price REAL,
                exit_price REAL,
                checked_at TEXT NOT NULL,
                FOREIGN KEY(signal_id)
                    REFERENCES signals(id)
            )
            """
        )
        await db.commit()
    logger.info(
        "Database initialized: %s",
        DB_PATH,
    )
# ============================================================
# USERS
# ============================================================
async def register_user(
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
) -> None:
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(
        DB_PATH
    ) as db:
        await db.execute(
            """
            INSERT INTO users (
                telegram_id,
                username,
                first_name,
                is_active,
                is_admin,
                created_at
            )
            VALUES (?, ?, ?, 1, 0, ?)
            ON CONFLICT(telegram_id)
            DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                is_active = 1
            """,
            (
                telegram_id,
                username,
                first_name,
                now,
            ),
        )
        await db.commit()
async def set_user_active(
    telegram_id: int,
    active: bool,
) -> None:
    async with aiosqlite.connect(
        DB_PATH
    ) as db:
        await db.execute(
            """
            UPDATE users
            SET is_active = ?
            WHERE telegram_id = ?
            """,
            (
                1 if active else 0,
                telegram_id,
            ),
        )
        await db.commit()
async def get_active_users() -> list[int]:
    async with aiosqlite.connect(
        DB_PATH
    ) as db:
        cursor = await db.execute(
            """
            SELECT telegram_id
            FROM users
            WHERE is_active = 1
            """
        )
        rows = await cursor.fetchall()
    return [
        int(row[0])
        for row in rows
    ]
async def get_all_users() -> list[int]:
    async with aiosqlite.connect(
        DB_PATH
    ) as db:
        cursor = await db.execute(
            """
            SELECT telegram_id
            FROM users
            """
        )
        rows = await cursor.fetchall()
    return [
        int(row[0])
        for row in rows
    ]
# ============================================================
# SIGNALS
# ============================================================
async def save_signal(
    symbol: str,
    direction: str,
    score: float,
    close_time: str,
    historical_probability: float | None = None,
    entry_price: float | None = None,
) -> int:
    created_at = datetime.utcnow().isoformat()
    async with aiosqlite.connect(
        DB_PATH
    ) as db:
        cursor = await db.execute(
            """
            INSERT INTO signals (
                symbol,
                direction,
                score,
                historical_probability,
                entry_price,
                exit_price,
                created_at,
                close_time,
                status,
                warning_sent,
                result_checked
            )
            VALUES (
                ?, ?, ?, ?, ?, NULL, ?, ?,
                'CREATED', 0, 0
            )
            """,
            (
                symbol,
                direction,
                float(score),
                historical_probability,
                entry_price,
                created_at,
                close_time,
            ),
        )
        await db.commit()
        signal_id = cursor.lastrowid
    if signal_id is None:
        raise RuntimeError(
            "Не удалось получить ID сигнала."
        )
    return int(signal_id)
async def get_signal(
    signal_id: int,
) -> dict[str, Any] | None:
    async with aiosqlite.connect(
        DB_PATH
    ) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT *
            FROM signals
            WHERE id = ?
            """,
            (signal_id,),
        )
        row = await cursor.fetchone()
    if row is None:
        return None
    return dict(row)
async def get_pending_warnings() -> list[dict[str, Any]]:
    async with aiosqlite.connect(
        DB_PATH
    ) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT *
            FROM signals
            WHERE warning_sent = 0
              AND status IN (
                  'CREATED',
                  'WARNING_SENT'
              )
            ORDER BY close_time ASC
            """
        )
        rows = await cursor.fetchall()
    return [
        dict(row)
        for row in rows
    ]
async def mark_warning_sent(
    signal_id: int,
) -> None:
    async with aiosqlite.connect(
        DB_PATH
    ) as db:
        await db.execute(
            """
            UPDATE signals
            SET
                warning_sent = 1,
                status = 'WARNING_SENT'
            WHERE id = ?
            """,
            (signal_id,),
        )
        await db.commit()
async def get_pending_results() -> list[dict[str, Any]]:
    async with aiosqlite.connect(
        DB_PATH
    ) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT *
            FROM signals
            WHERE result_checked = 0
              AND status IN (
                  'CREATED',
                  'WARNING_SENT'
              )
            ORDER BY close_time ASC
            """
        )
        rows = await cursor.fetchall()
    return [
        dict(row)
        for row in rows
    ]
async def save_signal_result(
    signal_id: int,
    result: str,
    exit_price: float | None,
) -> None:
    checked_at = datetime.utcnow().isoformat()
    normalized = result.upper()
    if normalized not in {
        "WIN",
        "LOSS",
        "DRAW",
        "ERROR",
    }:
        raise ValueError(
            f"Unknown signal result: {result}"
        )
    if normalized == "WIN":
        status = "WIN"
    elif normalized == "LOSS":
        status = "LOSS"
    elif normalized == "DRAW":
        status = "DRAW"
    else:
        status = "ERROR"
    async with aiosqlite.connect(
        DB_PATH
    ) as db:
        cursor = await db.execute(
            """
            SELECT entry_price
            FROM signals
            WHERE id = ?
            """,
            (signal_id,),
        )
        row = await cursor.fetchone()
        entry_price = (
            row[0]
            if row is not None
            else None
        )
        await db.execute(
            """
            UPDATE signals
            SET
                exit_price = ?,
                status = ?,
                result_checked = 1
            WHERE id = ?
            """,
            (
                exit_price,
                status,
                signal_id,
            ),
        )
        await db.execute(
            """
            INSERT INTO signal_statistics (
                signal_id,
                result,
                entry_price,
                exit_price,
                checked_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                signal_id,
                normalized,
                entry_price,
                exit_price,
                checked_at,
            ),
        )
        await db.commit()
# ============================================================
# STATISTICS
# ============================================================
async def get_signal_statistics() -> dict[str, float | int]:
    async with aiosqlite.connect(
        DB_PATH
    ) as db:
        cursor = await db.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(
                    CASE
                        WHEN result = 'WIN'
                        THEN 1
                        ELSE 0
                    END
                ) AS wins,
                SUM(
                    CASE
                        WHEN result = 'LOSS'
                        THEN 1
                        ELSE 0
                    END
                ) AS losses,
                SUM(
                    CASE
                        WHEN result = 'DRAW'
                        THEN 1
                        ELSE 0
                    END
                ) AS draws
            FROM signal_statistics
            """
        )
        row = await cursor.fetchone()
    total = int(
        row[0] or 0
    )
    wins = int(
        row[1] or 0
    )
    losses = int(
        row[2] or 0
    )
    draws = int(
        row[3] or 0
    )
    decisive = (
        wins + losses
    )
    if decisive:
        win_rate = (
            wins
            / decisive
            * 100
        )
    else:
        win_rate = 0.0
    return {
        "total": total,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "win_rate": win_rate,
    }
