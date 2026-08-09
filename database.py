from __future__ import annotations
import logging
from datetime import datetime
from typing import Any
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
# ============================================================
# DATABASE ENGINE
# ============================================================
def normalize_database_url(
    url: str,
) -> str:
    url = url.strip()
    if url.startswith(
        "postgres://"
    ):
        url = url.replace(
            "postgres://",
            "postgresql+asyncpg://",
            1,
        )
    elif url.startswith(
        "postgresql://"
    ):
        url = url.replace(
            "postgresql://",
            "postgresql+asyncpg://",
            1,
        )
    return url
DATABASE_URL_NORMALIZED = (
    normalize_database_url(
        DATABASE_URL
    )
)
engine = create_async_engine(
    DATABASE_URL_NORMALIZED,
    echo=False,
    pool_pre_ping=True,
)
SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
# ============================================================
# BASE
# ============================================================
class Base(DeclarativeBase):
    pass
# ============================================================
# USER
# ============================================================
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
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    is_admin: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
# ============================================================
# SIGNAL
# ============================================================
class Signal(Base):
    __tablename__ = "signals"
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    symbol: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    direction: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    historical_probability: Mapped[
        float | None
    ] = mapped_column(
        Float,
        nullable=True,
    )
    close_time: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    entry_price: Mapped[
        float | None
    ] = mapped_column(
        Float,
        nullable=True,
    )
    exit_price: Mapped[
        float | None
    ] = mapped_column(
        Float,
        nullable=True,
    )
    result: Mapped[
        str | None
    ] = mapped_column(
        String(20),
        nullable=True,
        index=True,
    )
    result_checked: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )
    checked_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime,
        nullable=True,
    )
# ============================================================
# INIT DATABASE
# ============================================================
async def init_db():
    logger.info(
        "Initializing database..."
    )
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all
        )
    logger.info(
        "Database initialized."
    )
# ============================================================
# USER FUNCTIONS
# ============================================================
async def get_or_create_user(
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
) -> User:
    async with SessionLocal() as session:
        result = await session.execute(
            select(User).where(
                User.telegram_id
                == telegram_id
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
            if username is not None:
                user.username = username
            if first_name is not None:
                user.first_name = first_name
            user.is_active = True
        await session.commit()
        await session.refresh(
            user
        )
        return user
async def set_user_active(
    telegram_id: int,
    active: bool,
):
    async with SessionLocal() as session:
        result = await session.execute(
            select(User).where(
                User.telegram_id
                == telegram_id
            )
        )
        user = result.scalar_one_or_none()
        if user is None:
            return False
        user.is_active = active
        await session.commit()
        return True
async def get_active_users() -> list[int]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(
                User.telegram_id
            ).where(
                User.is_active.is_(True)
            )
        )
        return list(
            result.scalars().all()
        )
# ============================================================
# SIGNAL FUNCTIONS
# ============================================================
async def save_signal(
    symbol: str,
    direction: str,
    score: float,
    close_time: str,
    historical_probability: float | None = None,
    entry_price: float | None = None,
) -> int:
    async with SessionLocal() as session:
        signal = Signal(
            symbol=symbol,
            direction=direction,
            score=float(score),
            historical_probability=(
                historical_probability
            ),
            close_time=close_time,
            entry_price=entry_price,
            result=None,
            result_checked=False,
        )
        session.add(signal)
        await session.commit()
        await session.refresh(
            signal
        )
        logger.info(
            "Signal #%s saved.",
            signal.id,
        )
        return signal.id
async def get_signal(
    signal_id: int,
) -> Signal | None:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Signal).where(
                Signal.id == signal_id
            )
        )
        return result.scalar_one_or_none()
async def get_pending_signals() -> list[Signal]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Signal)
            .where(
                Signal.result_checked.is_(False)
            )
            .order_by(
                Signal.created_at.asc()
            )
        )
        return list(
            result.scalars().all()
        )
async def set_signal_entry_price(
    signal_id: int,
    entry_price: float,
) -> bool:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Signal).where(
                Signal.id == signal_id
            )
        )
        signal = (
            result.scalar_one_or_none()
        )
        if signal is None:
            return False
        signal.entry_price = float(
            entry_price
        )
        await session.commit()
        return True
async def set_signal_result(
    signal_id: int,
    result_value: str,
    exit_price: float | None = None,
) -> bool:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Signal).where(
                Signal.id == signal_id
            )
        )
        signal = (
            result.scalar_one_or_none()
        )
        if signal is None:
            return False
        signal.result = (
            result_value.upper()
        )
        if exit_price is not None:
            signal.exit_price = float(
                exit_price
            )
        signal.result_checked = True
        signal.checked_at = (
            datetime.utcnow()
        )
        await session.commit()
        logger.info(
            "Signal #%s result: %s",
            signal_id,
            signal.result,
        )
        return True
# ============================================================
# STATISTICS
# ============================================================
async def get_signal_statistics() -> dict[str, Any]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Signal)
            .where(
                Signal.result_checked.is_(True)
            )
        )
        signals = list(
            result.scalars().all()
        )
    total = len(signals)
    wins = sum(
        1
        for signal in signals
        if signal.result == "WIN"
    )
    losses = sum(
        1
        for signal in signals
        if signal.result == "LOSS"
    )
    if total:
        win_rate = (
            wins / total * 100
        )
    else:
        win_rate = 0.0
    return {
        "total": total,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
    }
# ============================================================
# SHUTDOWN
# ============================================================
async def close_db():
    await engine.dispose()
    logger.info(
        "Database connection closed."
    )
