from __future__ import annotations

import logging
import os
from typing import Any

import asyncpg

logger = logging.getLogger("database")

DATABASE_URL = os.getenv("DATABASE_URL", "")

_pool: asyncpg.Pool | None = None


def _normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace(
            "postgres://",
            "postgresql://",
            1,
        )

    return url


async def init_db() -> None:
    global _pool

    if _pool is not None:
        return

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL не установлен."
        )

    database_url = _normalize_database_url(
        DATABASE_URL
    )

    _pool = await asyncpg.create_pool(
        dsn=database_url,
        min_size=1,
        max_size=5,
        command_timeout=20,
    )

    async with _pool.acquire() as conn:

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                telegram_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                is_admin BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS signals (
                id BIGSERIAL PRIMARY KEY,

                symbol TEXT NOT NULL,

                direction TEXT NOT NULL,

                score DOUBLE PRECISION NOT NULL,

                historical_probability
                    DOUBLE PRECISION,

                signal_time TEXT NOT NULL,

                close_time TEXT NOT NULL,

                result TEXT NOT NULL DEFAULT 'PENDING',

                entry_price
                    DOUBLE PRECISION,

                exit_price
                    DOUBLE PRECISION,

                created_at TIMESTAMPTZ
                    NOT NULL DEFAULT NOW(),

                checked_at TIMESTAMPTZ
            )
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_signals_result
            ON signals(result)
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_signals_symbol
            ON signals(symbol)
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_signals_created_at
            ON signals(created_at)
            """
        )

    logger.info(
        "Database initialized."
    )


async def close_db() -> None:
    global _pool

    if _pool is not None:
        await _pool.close()
        _pool = None

        logger.info(
            "Database connection closed."
        )


def _get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError(
            "Database не инициализирована."
        )

    return _pool


async def register_user(
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
) -> None:

    pool = _get_pool()

    async with pool.acquire() as conn:

        await conn.execute(
            """
            INSERT INTO users (
                telegram_id,
                username,
                first_name,
                is_active,
                last_seen_at
            )
            VALUES ($1, $2, $3, TRUE, NOW())
            ON CONFLICT (telegram_id)
            DO UPDATE SET
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                is_active = TRUE,
                last_seen_at = NOW()
            """,
            telegram_id,
            username,
            first_name,
        )


async def set_user_active(
    telegram_id: int,
    active: bool,
) -> None:

    pool = _get_pool()

    async with pool.acquire() as conn:

        await conn.execute(
            """
            UPDATE users
            SET
                is_active = $2,
                last_seen_at = NOW()
            WHERE telegram_id = $1
            """,
            telegram_id,
            active,
        )


async def get_active_users() -> list[int]:

    pool = _get_pool()

    async with pool.acquire() as conn:

        rows = await conn.fetch(
            """
            SELECT telegram_id
            FROM users
            WHERE is_active = TRUE
            ORDER BY telegram_id
            """
        )

    return [
        int(row["telegram_id"])
        for row in rows
    ]


async def save_signal(
    symbol: str,
    direction: str,
    score: float,
    close_time: str,
    historical_probability: float | None = None,
    signal_time: str | None = None,
) -> int:

    pool = _get_pool()

    if signal_time is None:
        from time_utils import format_moscow_time
        from time_utils import now_moscow

        signal_time = format_moscow_time(
            now_moscow()
        )

    async with pool.acquire() as conn:

        signal_id = await conn.fetchval(
            """
            INSERT INTO signals (
                symbol,
                direction,
                score,
                historical_probability,
                signal_time,
                close_time,
                result
            )
            VALUES (
                $1,
                $2,
                $3,
                $4,
                $5,
                $6,
                'PENDING'
            )
            RETURNING id
            """,
            symbol,
            direction,
            float(score),
            historical_probability,
            signal_time,
            close_time,
        )

    return int(signal_id)


async def get_pending_signals() -> list[dict[str, Any]]:

    pool = _get_pool()

    async with pool.acquire() as conn:

        rows = await conn.fetch(
            """
            SELECT
                id,
                symbol,
                direction,
                score,
                historical_probability,
                signal_time,
                close_time,
                result,
                entry_price,
                exit_price,
                created_at
            FROM signals
            WHERE result = 'PENDING'
            ORDER BY id ASC
            """
        )

    return [
        dict(row)
        for row in rows
    ]


async def get_signal(
    signal_id: int,
) -> dict[str, Any] | None:

    pool = _get_pool()

    async with pool.acquire() as conn:

        row = await conn.fetchrow(
            """
            SELECT
                id,
                symbol,
                direction,
                score,
                historical_probability,
                signal_time,
                close_time,
                result,
                entry_price,
                exit_price,
                created_at
            FROM signals
            WHERE id = $1
            """,
            signal_id,
        )

    if row is None:
        return None

    return dict(row)


async def update_signal_result(
    signal_id: int,
    result: str,
    entry_price: float,
    exit_price: float,
) -> None:

    pool = _get_pool()

    async with pool.acquire() as conn:

        await conn.execute(
            """
            UPDATE signals
            SET
                result = $2,
                entry_price = $3,
                exit_price = $4,
                checked_at = NOW()
            WHERE id = $1
            """,
            signal_id,
            result,
            float(entry_price),
            float(exit_price),
        )


async def get_signal_statistics() -> dict[str, float | int]:

    pool = _get_pool()

    async with pool.acquire() as conn:

        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (
                    WHERE result IN ('WIN', 'LOSS', 'DRAW')
                ) AS total,

                COUNT(*) FILTER (
                    WHERE result = 'WIN'
                ) AS wins,

                COUNT(*) FILTER (
                    WHERE result = 'LOSS'
                ) AS losses,

                COUNT(*) FILTER (
                    WHERE result = 'DRAW'
                ) AS draws,

                COUNT(*) FILTER (
                    WHERE result = 'PENDING'
                ) AS pending
            FROM signals
            """
        )

    total = int(row["total"] or 0)
    wins = int(row["wins"] or 0)
    losses = int(row["losses"] or 0)
    draws = int(row["draws"] or 0)
    pending = int(row["pending"] or 0)

    decisive = wins + losses

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
        "pending": pending,
        "win_rate": win_rate,
    }
