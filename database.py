import aiosqlite

from config import DB_PATH


CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE NOT NULL,
    username TEXT,
    first_name TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


CREATE_APPLICATIONS = """
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    username TEXT,
    text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TEXT
);
"""


CREATE_SIGNALS = """
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    score REAL NOT NULL,
    close_time TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(CREATE_USERS)
        await db.execute(CREATE_APPLICATIONS)
        await db.execute(CREATE_SIGNALS)

        await db.commit()


async def add_user(
    telegram_id: int,
    username: str | None,
    first_name: str | None,
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO users (
                telegram_id,
                username,
                first_name
            )
            VALUES (?, ?, ?)
            ON CONFLICT(telegram_id)
            DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name
            """,
            (
                telegram_id,
                username,
                first_name,
            ),
        )

        await db.commit()


async def get_active_users():
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT telegram_id
            FROM users
            WHERE is_active = 1
            """
        )

        rows = await cursor.fetchall()

        return [
            row[0]
            for row in rows
        ]


async def create_application(
    telegram_id: int,
    username: str | None,
    text: str,
):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO applications (
                telegram_id,
                username,
                text
            )
            VALUES (?, ?, ?)
            """,
            (
                telegram_id,
                username,
                text,
            ),
        )

        await db.commit()

        return cursor.lastrowid


async def get_application(application_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT
                id,
                telegram_id,
                username,
                text,
                status
            FROM applications
            WHERE id = ?
            """,
            (application_id,),
        )

        return await cursor.fetchone()


async def update_application(
    application_id: int,
    status: str,
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE applications
            SET
                status = ?,
                processed_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                status,
                application_id,
            ),
        )

        await db.commit()


async def save_signal(
    symbol: str,
    direction: str,
    score: float,
    close_time: str,
):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO signals (
                symbol,
                direction,
                score,
                close_time
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                symbol,
                direction,
                score,
                close_time,
            ),
        )

        await db.commit()

        return cursor.lastrowid

async def update_signal_result(
    signal_id: int,
    status: str,
):
    async with aiosqlite.connect(DB_PATH) as db:

        await db.execute(
            """
            UPDATE signals
            SET status = ?
            WHERE id = ?
            """,
            (
                status,
                signal_id,
            ),
        )

        await db.commit()


async def get_signal_statistics():
    async with aiosqlite.connect(DB_PATH) as db:

        cursor = await db.execute(
            """
            SELECT
                COUNT(*),
                SUM(
                    CASE
                        WHEN status = 'win'
                        THEN 1
                        ELSE 0
                    END
                ),
                SUM(
                    CASE
                        WHEN status = 'loss'
                        THEN 1
                        ELSE 0
                    END
                )
            FROM signals
            """
        )

        row = await cursor.fetchone()

        total = row[0] or 0
        wins = row[1] or 0
        losses = row[2] or 0

        if total:

            win_rate = (
                wins
                / total
                * 100
            )

        else:

            win_rate = 0.0

        return {
            "total": total,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
        }
