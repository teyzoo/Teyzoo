from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    Integer,
    String,
    Text,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
)

from config import DATABASE_URL


logger = logging.getLogger("database")


# =========================================================
# DATABASE URL
# =========================================================

def normalize_database_url(
    url: str,
) -> str:
    if url.startswith("postgres://"):
        return url.replace(
            "postgres://",
            "postgresql+asyncpg://",
            1,
        )

    if url.startswith("postgresql://"):
        return url.replace(
            "postgresql://",
            "postgresql+asyncpg://",
            1,
        )

    return url


DATABASE_URL_ASYNC = normalize_database_url(
    DATABASE_URL
)


# =========================================================
# ENGINE
# =========================================================

engine = create_async_engine(
    DATABASE_URL_ASYNC,
    pool_pre_ping=True,
    pool_recycle=300,
)


SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# =========================================================
# BASE
# =========================================================

class Base(DeclarativeBase):
    pass


# =========================================================
# USER
# =========================================================

class UserModel(Base):

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    telegram_id: Mapped[int] = mapped_column(
        Integer,
        unique=True,
        index=True,
        nullable=False,
    )

    username: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    first_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    last_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


# =========================================================
# SIGNAL
# =========================================================

class SignalModel(Base):

    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    symbol: Mapped[str] = mapped_column(
        String(32),
        index=True,
        nullable=False,
    )

    direction: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )

    entry_price: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    exit_price: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    close_time: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    historical_probability: Mapped[
        float | None
    ] = mapped_column(
        Float,
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        default="PENDING",
        index=True,
        nullable=False,
    )

    result_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    resolved_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


# =========================================================
# APPLICATION
# =========================================================

class ApplicationModel(Base):

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    telegram_id: Mapped[int] = mapped_column(
        Integer,
        index=True,
        nullable=False,
    )

    text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        default="NEW",
        index=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


# =========================================================
# INIT / CLOSE
# =========================================================

async def init_database() -> None:

    async with engine.begin() as connection:

        await connection.run_sync(
            Base.metadata.create_all
        )

    logger.info(
        "Database initialized."
    )


async def close_database() -> None:

    await engine.dispose()

    logger.info(
        "Database connection closed."
    )


# =========================================================
# USERS
# =========================================================

async def upsert_user(
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> UserModel:

    async with SessionLocal() as session:

        result = await session.execute(
            select(UserModel).where(
                UserModel.telegram_id == telegram_id
            )
        )

        user = result.scalar_one_or_none()

        if user is None:

            user = UserModel(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
            )

            session.add(user)

        else:

            if username is not None:
                user.username = username

            if first_name is not None:
                user.first_name = first_name

            if last_name is not None:
                user.last_name = last_name

        await session.commit()

        await session.refresh(user)

        return user


async def get_or_create_user(
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> UserModel:

    async with SessionLocal() as session:

        result = await session.execute(
            select(UserModel).where(
                UserModel.telegram_id == telegram_id
            )
        )

        user = result.scalar_one_or_none()

        if user is None:

            user = UserModel(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
            )

            session.add(user)

            await session.commit()
            await session.refresh(user)

            return user

        changed = False

        if username is not None and user.username != username:
            user.username = username
            changed = True

        if first_name is not None and user.first_name != first_name:
            user.first_name = first_name
            changed = True

        if last_name is not None and user.last_name != last_name:
            user.last_name = last_name
            changed = True

        if changed:
            await session.commit()
            await session.refresh(user)

        return user


async def get_active_users() -> list[int]:

    async with SessionLocal() as session:

        result = await session.execute(
            select(
                UserModel.telegram_id
            ).order_by(
                UserModel.id.asc()
            )
        )

        return [
            int(row[0])
            for row in result.all()
        ]


# =========================================================
# SIGNALS
# =========================================================

async def save_signal(
    symbol: str,
    direction: str,
    score: float,
    close_time: str,
    historical_probability: float | None = None,
    entry_price: float | None = None,
) -> int:

    async with SessionLocal() as session:

        signal = SignalModel(
            symbol=symbol,
            direction=direction,
            score=score,
            close_time=close_time,
            historical_probability=(
                historical_probability
            ),
            entry_price=entry_price,
            status="PENDING",
        )

        session.add(signal)

        await session.flush()

        signal_id = signal.id

        await session.commit()

        return signal_id


async def get_signal(
    signal_id: int,
) -> SignalModel | None:

    async with SessionLocal() as session:

        result = await session.execute(
            select(SignalModel).where(
                SignalModel.id == signal_id
            )
        )

        return result.scalar_one_or_none()


async def get_latest_signal() -> SignalModel | None:

    async with SessionLocal() as session:

        result = await session.execute(
            select(SignalModel)
            .order_by(
                SignalModel.created_at.desc()
            )
            .limit(1)
        )

        return result.scalar_one_or_none()


async def get_latest_pending_signal() -> SignalModel | None:

    async with SessionLocal() as session:

        result = await session.execute(
            select(SignalModel)
            .where(
                SignalModel.status == "PENDING"
            )
            .order_by(
                SignalModel.created_at.desc()
            )
            .limit(1)
        )

        return result.scalar_one_or_none()


async def get_pending_signals() -> list[SignalModel]:

    async with SessionLocal() as session:

        result = await session.execute(
            select(SignalModel)
            .where(
                SignalModel.status == "PENDING"
            )
            .order_by(
                SignalModel.created_at.asc()
            )
        )

        return list(
            result.scalars().all()
        )


async def update_signal_result(
    signal_id: int,
    status: str,
    exit_price: float | None = None,
    reason: str | None = None,
) -> bool:

    async with SessionLocal() as session:

        result = await session.execute(
            select(SignalModel).where(
                SignalModel.id == signal_id
            )
        )

        signal = result.scalar_one_or_none()

        if signal is None:
            return False

        signal.status = status

        if exit_price is not None:
            signal.exit_price = exit_price

        if reason is not None:
            signal.result_reason = reason

        signal.resolved_at = datetime.now(
            timezone.utc
        )

        await session.commit()

        return True


# =========================================================
# SIGNAL STATISTICS
# =========================================================

async def get_signal_statistics() -> dict[str, Any]:

    async with SessionLocal() as session:

        result = await session.execute(
            select(SignalModel)
        )

        signals = list(
            result.scalars().all()
        )

    total = len(signals)

    wins = sum(
        signal.status == "WON"
        for signal in signals
    )

    losses = sum(
        signal.status == "LOST"
        for signal in signals
    )

    draws = sum(
        signal.status == "DRAW"
        for signal in signals
    )

    pending = sum(
        signal.status == "PENDING"
        for signal in signals
    )

    cancelled = sum(
        signal.status == "CANCELLED"
        for signal in signals
    )

    finished = (
        wins
        + losses
        + draws
    )

    win_rate = (
        wins / finished * 100
        if finished
        else 0.0
    )

    return {
        "total": total,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "pending": pending,
        "cancelled": cancelled,
        "finished": finished,
        "winrate": win_rate,
        "win_rate": win_rate,
    }


# =========================================================
# APPLICATIONS
# =========================================================

async def create_application(
    telegram_id: int,
    text: str,
) -> int:

    async with SessionLocal() as session:

        application = ApplicationModel(
            telegram_id=telegram_id,
            text=text,
            status="NEW",
        )

        session.add(application)

        await session.flush()

        application_id = application.id

        await session.commit()

        return application_id


async def get_application(
    application_id: int,
) -> ApplicationModel | None:

    async with SessionLocal() as session:

        result = await session.execute(
            select(ApplicationModel).where(
                ApplicationModel.id
                == application_id
            )
        )

        return result.scalar_one_or_none()


async def get_new_applications() -> list[
    ApplicationModel
]:

    async with SessionLocal() as session:

        result = await session.execute(
            select(ApplicationModel)
            .where(
                ApplicationModel.status
                == "NEW"
            )
            .order_by(
                ApplicationModel.created_at.asc()
            )
        )

        return list(
            result.scalars().all()
        )


async def update_application_status(
    application_id: int,
    status: str,
) -> bool:

    async with SessionLocal() as session:

        result = await session.execute(
            select(ApplicationModel).where(
                ApplicationModel.id
                == application_id
            )
        )

        application = (
            result.scalar_one_or_none()
        )

        if application is None:
            return False

        application.status = status

        await session.commit()

        return True


# =========================================================
# EXPORTS
# =========================================================

__all__ = [
    "Base",
    "UserModel",
    "SignalModel",
    "ApplicationModel",
    "SessionLocal",
    "engine",
    "init_database",
    "close_database",
    "upsert_user",
    "get_or_create_user",
    "get_active_users",
    "save_signal",
    "get_signal",
    "get_latest_signal",
    "get_latest_pending_signal",
    "get_pending_signals",
    "update_signal_result",
    "get_signal_statistics",
    "create_application",
    "get_application",
    "get_new_applications",
    "update_application_status",
]
