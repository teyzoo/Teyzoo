from __future__ import annotations

import logging
from datetime import datetime
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


logger = logging.getLogger(
    "database"
)


def normalize_database_url(
    url: str,
) -> str:

    if url.startswith(
        "postgres://"
    ):

        return url.replace(
            "postgres://",
            "postgresql+asyncpg://",
            1,
        )

    if url.startswith(
        "postgresql://"
    ):

        return url.replace(
            "postgresql://",
            "postgresql+asyncpg://",
            1,
        )

    return url


DATABASE_URL_ASYNC = (
    normalize_database_url(
        DATABASE_URL
    )
)


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


class Base(DeclarativeBase):
    pass


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
    )

    username: Mapped[str | None] = (
        mapped_column(
            String(255),
            nullable=True,
        )
    )

    first_name: Mapped[str | None] = (
        mapped_column(
            String(255),
            nullable=True,
        )
    )

    last_name: Mapped[str | None] = (
        mapped_column(
            String(255),
            nullable=True,
        )
    )

    created_at: Mapped[datetime] = (
        mapped_column(
            DateTime(timezone=True),
            default=datetime.utcnow,
        )
    )


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
    )

    direction: Mapped[str] = mapped_column(
        String(16),
    )

    entry_price: Mapped[float | None] = (
        mapped_column(
            Float,
            nullable=True,
        )
    )

    exit_price: Mapped[float | None] = (
        mapped_column(
            Float,
            nullable=True,
        )
    )

    score: Mapped[float] = mapped_column(
        Float,
    )

    close_time: Mapped[str] = mapped_column(
        String(64),
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
    )

    result_reason: Mapped[str | None] = (
        mapped_column(
            Text,
            nullable=True,
        )
    )

    created_at: Mapped[datetime] = (
        mapped_column(
            DateTime(timezone=True),
            default=datetime.utcnow,
        )
    )

    resolved_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


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


async def get_active_users() -> list[int]:

    async with SessionLocal() as session:

        result = await session.execute(
            select(
                UserModel.telegram_id
            )
        )

        return [
            int(row[0])
            for row in result.all()
        ]


async def upsert_user(
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> None:

    async with SessionLocal() as session:

        result = await session.execute(
            select(UserModel).where(
                UserModel.telegram_id
                == telegram_id
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

            user.username = username
            user.first_name = first_name
            user.last_name = last_name

        await session.commit()


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
                SignalModel.id
                == signal_id
            )
        )

        return result.scalar_one_or_none()


async def get_pending_signals() -> list[
    SignalModel
]:

    async with SessionLocal() as session:

        result = await session.execute(
            select(SignalModel)
            .where(
                SignalModel.status
                == "PENDING"
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
                SignalModel.id
                == signal_id
            )
        )

        signal = (
            result.scalar_one_or_none()
        )

        if signal is None:
            return False

        signal.status = status
        signal.exit_price = exit_price
        signal.result_reason = reason
        signal.resolved_at = datetime.utcnow()

        await session.commit()

        return True


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

    pending = sum(
        signal.status == "PENDING"
        for signal in signals
    )

    finished = wins + losses

    winrate = (
        wins / finished * 100
        if finished
        else 0.0
    )

    return {
        "total": total,
        "wins": wins,
        "losses": losses,
        "pending": pending,
        "winrate": winrate,
    }
