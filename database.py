from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import (
    Boolean,
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


engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)


SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


class User(Base):

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    telegram_id: Mapped[int] = mapped_column(
        Integer,
        unique=True,
        index=True,
    )

    username: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    first_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )


class Signal(Base):

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

    score: Mapped[float] = mapped_column(
        Float,
    )

    historical_probability: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    close_time: Mapped[str] = mapped_column(
        String(64),
    )

    status: Mapped[str] = mapped_column(
        String(32),
        default="WAITING",
        index=True,
    )

    result: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )


class Application(Base):

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    telegram_id: Mapped[int] = mapped_column(
        Integer,
        index=True,
    )

    text: Mapped[str] = mapped_column(
        Text,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        default="NEW",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )


async def init_db() -> None:

    async with engine.begin() as connection:

        await connection.run_sync(
            Base.metadata.create_all
        )

    logger.info(
        "Database initialized."
    )


async def get_active_users() -> list[int]:

    async with SessionLocal() as session:

        result = await session.execute(
            select(User.telegram_id)
            .where(
                User.is_active.is_(True)
            )
        )

        return list(
            result.scalars().all()
        )


async def get_or_create_user(
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
) -> User:

    async with SessionLocal() as session:

        result = await session.execute(
            select(User)
            .where(
                User.telegram_id == telegram_id
            )
        )

        user = result.scalar_one_or_none()

        if user is None:

            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                is_active=True,
            )

            session.add(user)

        else:

            user.username = username
            user.first_name = first_name
            user.is_active = True

        await session.commit()

        await session.refresh(user)

        return user


async def deactivate_user(
    telegram_id: int,
) -> None:

    async with SessionLocal() as session:

        result = await session.execute(
            select(User)
            .where(
                User.telegram_id == telegram_id
            )
        )

        user = result.scalar_one_or_none()

        if user:

            user.is_active = False

            await session.commit()


async def save_signal(
    symbol: str,
    direction: str,
    score: float,
    close_time: str,
    historical_probability: float | None = None,
) -> int:

    async with SessionLocal() as session:

        signal = Signal(
            symbol=symbol,
            direction=direction,
            score=score,
            close_time=close_time,
            historical_probability=(
                historical_probability
            ),
            status="WAITING",
        )

        session.add(signal)

        await session.commit()

        await session.refresh(signal)

        return signal.id


async def get_signal(
    signal_id: int,
) -> Signal | None:

    async with SessionLocal() as session:

        result = await session.execute(
            select(Signal)
            .where(
                Signal.id == signal_id
            )
        )

        return result.scalar_one_or_none()


async def update_signal_result(
    signal_id: int,
    result_value: str,
    won: bool,
) -> None:

    async with SessionLocal() as session:

        result = await session.execute(
            select(Signal)
            .where(
                Signal.id == signal_id
            )
        )

        signal = result.scalar_one_or_none()

        if signal is None:
            return

        signal.result = result_value

        signal.status = (
            "WON"
            if won
            else "LOST"
        )

        await session.commit()


async def create_application(
    telegram_id: int,
    text: str,
) -> int:

    async with SessionLocal() as session:

        application = Application(
            telegram_id=telegram_id,
            text=text,
            status="NEW",
        )

        session.add(application)

        await session.commit()

        await session.refresh(
            application
        )

        return application.id


async def get_new_applications() -> list[Application]:

    async with SessionLocal() as session:

        result = await session.execute(
            select(Application)
            .where(
                Application.status == "NEW"
            )
            .order_by(
                Application.created_at.asc()
            )
        )

        return list(
            result.scalars().all()
        )


async def update_application_status(
    application_id: int,
    status: str,
) -> None:

    async with SessionLocal() as session:

        result = await session.execute(
            select(Application)
            .where(
                Application.id == application_id
            )
        )

        application = (
            result.scalar_one_or_none()
        )

        if application is None:
            return

        application.status = status

        await session.commit()
