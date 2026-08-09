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
    func,
    select,
    update,
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
# ============================================================
# DATABASE ENGINE
# ============================================================
def normalize_database_url(
    url: str,
) -> str:
    if not url:
        raise ValueError(
            "DATABASE_URL не задан."
        )
    #
    # Render/PostgreSQL иногда передаёт:
    #
    # postgresql://...
    #
    # SQLAlchemy async требует:
    #
    # postgresql+asyncpg://...
    #
    if url.startswith(
        "postgresql://"
    ):
        return url.replace(
            "postgresql://",
            "postgresql+asyncpg://",
            1,
        )
    if url.startswith(
        "postgres://"
    ):
        return url.replace(
            "postgres://",
            "postgresql+asyncpg://",
            1,
        )
    return url
DATABASE_URL = normalize_database_url(
    DATABASE_URL
)
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)
SessionLocal = (
    async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
)
# ============================================================
# BASE
# ============================================================
class Base(
    DeclarativeBase
):
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
    username: Mapped[
        str | None
    ] = mapped_column(
        String(255),
        nullable=True,
    )
    first_name: Mapped[
        str | None
    ] = mapped_column(
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
    created_at: Mapped[
        datetime
    ] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[
        datetime
    ] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
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
    # --------------------------------------------------------
    # Market
    # --------------------------------------------------------
    symbol: Mapped[str] = mapped_column(
        String(32),
        index=True,
        nullable=False,
    )
    direction: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )
    # --------------------------------------------------------
    # Analysis
    # --------------------------------------------------------
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
    confirmations: Mapped[
        int | None
    ] = mapped_column(
        Integer,
        nullable=True,
    )
    total_checks: Mapped[
        int | None
    ] = mapped_column(
        Integer,
        nullable=True,
    )
    reasons: Mapped[
        str | None
    ] = mapped_column(
        Text,
        nullable=True,
    )
    # --------------------------------------------------------
    # Time
    # --------------------------------------------------------
    created_at: Mapped[
        datetime
    ] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )
    close_time: Mapped[
        str
    ] = mapped_column(
        String(64),
        nullable=False,
    )
    close_datetime: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
    )
    # --------------------------------------------------------
    # Prices
    # --------------------------------------------------------
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
    # --------------------------------------------------------
    # Result
    # --------------------------------------------------------
    status: Mapped[
        str
    ] = mapped_column(
        String(16),
        default="PENDING",
        nullable=False,
        index=True,
    )
    result_checked_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime,
        nullable=True,
    )
    # --------------------------------------------------------
    # Extra
    # --------------------------------------------------------
    error_message: Mapped[
        str | None
    ] = mapped_column(
        Text,
        nullable=True,
    )
# ============================================================
# INIT DATABASE
# ============================================================
async def init_db():
    """
    Создаёт таблицы, если их ещё нет.
    Для production желательно использовать
    Alembic migrations, но этот метод позволяет
    проекту нормально стартовать на чистой БД.
    """
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
# SESSION
# ============================================================
def get_session() -> AsyncSession:
    return SessionLocal()
# ============================================================
# USERS
# ============================================================
async def create_or_update_user(
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
            user.username = username
            user.first_name = first_name
            user.is_active = True
            user.updated_at = (
                datetime.utcnow()
            )
        await session.commit()
        await session.refresh(
            user
        )
        return user
async def deactivate_user(
    telegram_id: int,
):
    async with SessionLocal() as session:
        await session.execute(
            update(User)
            .where(
                User.telegram_id
                == telegram_id
            )
            .values(
                is_active=False,
                updated_at=datetime.utcnow(),
            )
        )
        await session.commit()
async def get_active_users() -> list[int]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(
                User.telegram_id
            )
            .where(
                User.is_active.is_(True)
            )
        )
        return list(
            result.scalars().all()
        )
async def get_user(
    telegram_id: int,
) -> User | None:
    async with SessionLocal() as session:
        result = await session.execute(
            select(User).where(
                User.telegram_id
                == telegram_id
            )
        )
        return (
            result.scalar_one_or_none()
        )
# ============================================================
# SAVE SIGNAL
# ============================================================
async def save_signal(
    symbol: str,
    direction: str,
    score: float,
    close_time: str,
    historical_probability: float | None = None,
    confirmations: int | None = None,
    total_checks: int | None = None,
    reasons: list[str] | None = None,
    close_datetime: datetime | None = None,
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
            confirmations=confirmations,
            total_checks=total_checks,
            reasons=(
                "\n".join(reasons)
                if reasons
                else None
            ),
            close_time=close_time,
            close_datetime=close_datetime,
            entry_price=entry_price,
            status="PENDING",
        )
        session.add(signal)
        await session.commit()
        await session.refresh(
            signal
        )
        logger.info(
            "Saved signal #%s: %s %s",
            signal.id,
            symbol,
            direction,
        )
        return signal.id
# ============================================================
# GET SIGNAL
# ============================================================
async def get_signal(
    signal_id: int,
) -> Signal | None:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Signal).where(
                Signal.id
                == signal_id
            )
        )
        return (
            result.scalar_one_or_none()
        )
# ============================================================
# GET PENDING SIGNALS
# ============================================================
async def get_pending_signals() -> list[
    Signal
]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Signal)
            .where(
                Signal.status
                == "PENDING"
            )
            .order_by(
                Signal.created_at.asc()
            )
        )
        return list(
            result.scalars().all()
        )
# ============================================================
# GET SIGNALS READY FOR CHECK
# ============================================================
async def get_signals_ready_for_check(
    now: datetime,
) -> list[Signal]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Signal)
            .where(
                Signal.status
                == "PENDING"
            )
            .where(
                Signal.close_datetime
                <= now
            )
            .order_by(
                Signal.close_datetime.asc()
            )
        )
        return list(
            result.scalars().all()
        )
# ============================================================
# COMPLETE SIGNAL
# ============================================================
async def complete_signal(
    signal_id: int,
    status: str,
    exit_price: float,
    error_message: str | None = None,
) -> bool:
    status = status.upper()
    if status not in {
        "WIN",
        "LOSS",
        "ERROR",
    }:
        raise ValueError(
            "Некорректный status: "
            f"{status}"
        )
    async with SessionLocal() as session:
        result = await session.execute(
            select(Signal).where(
                Signal.id
                == signal_id
            )
        )
        signal = (
            result.scalar_one_or_none()
        )
        if signal is None:
            return False
        signal.status = status
        signal.exit_price = float(
            exit_price
        )
        signal.result_checked_at = (
            datetime.utcnow()
        )
        signal.error_message = (
            error_message
        )
        await session.commit()
        logger.info(
            "Signal #%s completed: %s",
            signal_id,
            status,
        )
        return True
# ============================================================
# UPDATE ENTRY PRICE
# ============================================================
async def set_signal_entry_price(
    signal_id: int,
    entry_price: float,
    close_datetime: datetime | None = None,
) -> bool:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Signal).where(
                Signal.id
                == signal_id
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
        if close_datetime is not None:
            signal.close_datetime = (
                close_datetime
            )
        await session.commit()
        return True
# ============================================================
# STATISTICS
# ============================================================
async def get_signal_statistics() -> dict[
    str,
    Any,
]:
    async with SessionLocal() as session:
        total_result = (
            await session.execute(
                select(
                    func.count(
                        Signal.id
                    )
                )
            )
        )
        total = (
            total_result.scalar()
            or 0
        )
        wins_result = (
            await session.execute(
                select(
                    func.count(
                        Signal.id
                    )
                )
                .where(
                    Signal.status
                    == "WIN"
                )
            )
        )
        wins = (
            wins_result.scalar()
            or 0
        )
        losses_result = (
            await session.execute(
                select(
                    func.count(
                        Signal.id
                    )
                )
                .where(
                    Signal.status
                    == "LOSS"
                )
            )
        )
        losses = (
            losses_result.scalar()
            or 0
        )
        pending_result = (
            await session.execute(
                select(
                    func.count(
                        Signal.id
                    )
                )
                .where(
                    Signal.status
                    == "PENDING"
                )
            )
        )
        pending = (
            pending_result.scalar()
            or 0
        )
        error_result = (
            await session.execute(
                select(
                    func.count(
                        Signal.id
                    )
                )
                .where(
                    Signal.status
                    == "ERROR"
                )
            )
        )
        errors = (
            error_result.scalar()
            or 0
        )
        completed = (
            wins + losses
        )
        if completed:
            win_rate = (
                wins
                / completed
                * 100
            )
        else:
            win_rate = 0.0
        return {
            "total": total,
            "wins": wins,
            "losses": losses,
            "pending": pending,
            "errors": errors,
            "completed": completed,
            "win_rate": win_rate,
        }
# ============================================================
# HISTORICAL RESULTS
# ============================================================
async def get_completed_signals(
    limit: int = 1000,
) -> list[Signal]:
    if limit < 1:
        limit = 1
    if limit > 10000:
        limit = 10000
    async with SessionLocal() as session:
        result = await session.execute(
            select(Signal)
            .where(
                Signal.status.in_(
                    [
                        "WIN",
                        "LOSS",
                    ]
                )
            )
            .order_by(
                Signal.created_at.desc()
            )
            .limit(limit)
        )
        return list(
            result.scalars().all()
        )
# ============================================================
# SHUTDOWN
# ============================================================
async def close_db():
    await engine.dispose()
    logger.info(
        "Database connection closed."
    )
