from __future__ import annotations
import logging
import os
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
logger = logging.getLogger("database")
# ============================================================
# DATABASE URL
# ============================================================
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./teyzus.db",
)
# Render/PostgreSQL иногда отдаёт postgres://
# или postgresql://.
if DATABASE_URL.startswith(
    "postgres://"
):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://",
        "postgresql+asyncpg://",
        1,
    )
elif DATABASE_URL.startswith(
    "postgresql://"
):
    DATABASE_URL = DATABASE_URL.replace(
        "postgresql://",
        "postgresql+asyncpg://",
        1,
    )
# ============================================================
# ENGINE
# ============================================================
engine = create_async_engine(
    DATABASE_URL,
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
        DateTime(timezone=True),
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
        String(32),
        nullable=False,
        index=True,
    )
    direction: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    # Цена на момент формирования сигнала.
    entry_price: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    # Фактическая цена после закрытия.
    exit_price: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    quality_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
    historical_probability: Mapped[
        float | None
    ] = mapped_column(
        Float,
        nullable=True,
    )
    confirmations: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    total_checks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="PENDING",
        index=True,
    )
    stage: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="ACTIVE",
    )
    close_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    checked_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    result_reason: Mapped[
        str | None
    ] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )
# ============================================================
# INIT DATABASE
# ============================================================
async def init_db() -> None:
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
            user.username = username
            user.first_name = first_name
            user.is_active = True
        await session.commit()
        await session.refresh(user)
        return user
async def set_user_active(
    telegram_id: int,
    active: bool,
) -> None:
    async with SessionLocal() as session:
        await session.execute(
            update(User)
            .where(
                User.telegram_id
                == telegram_id
            )
            .values(
                is_active=active
            )
        )
        await session.commit()
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
# SIGNAL CREATION
# ============================================================
async def save_signal(
    symbol: str,
    direction: str,
    score: float,
    close_time: str | datetime,
    historical_probability: float | None = None,
    entry_price: float | None = None,
    confirmations: int = 0,
    total_checks: int = 0,
) -> int:
    if isinstance(
        close_time,
        str,
    ):
        parsed_close_time = (
            _parse_datetime(
                close_time
            )
        )
    else:
        parsed_close_time = close_time
    async with SessionLocal() as session:
        signal = Signal(
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            quality_score=score,
            historical_probability=(
                historical_probability
            ),
            confirmations=confirmations,
            total_checks=total_checks,
            status="PENDING",
            stage="ACTIVE",
            close_time=parsed_close_time,
        )
        session.add(signal)
        await session.commit()
        await session.refresh(signal)
        logger.info(
            "Signal #%s saved.",
            signal.id,
        )
        return signal.id
# ============================================================
# GET PENDING SIGNALS
# ============================================================
async def get_pending_signals() -> list[Signal]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Signal)
            .where(
                Signal.status
                == "PENDING"
            )
            .order_by(
                Signal.close_time.asc()
            )
        )
        return list(
            result.scalars().all()
        )
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
        return result.scalar_one_or_none()
# ============================================================
# UPDATE SIGNAL RESULT
# ============================================================
async def update_signal_result(
    signal_id: int,
    status: str,
    entry_price: float,
    exit_price: float,
    checked_at: datetime,
    reason: str,
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
            logger.warning(
                "Signal #%s not found.",
                signal_id,
            )
            return False
        # Не разрешаем второй раз
        # обработать уже завершённый сигнал.
        if signal.status != "PENDING":
            logger.warning(
                "Signal #%s already has "
                "status %s.",
                signal_id,
                signal.status,
            )
            return False
        signal.status = status
        signal.stage = "FINISHED"
        signal.entry_price = (
            entry_price
        )
        signal.exit_price = (
            exit_price
        )
        signal.checked_at = checked_at
        signal.result_reason = reason
        await session.commit()
        logger.info(
            "Signal #%s -> %s",
            signal_id,
            status,
        )
        return True
# ============================================================
# STATISTICS
# ============================================================
async def get_signal_statistics() -> dict[str, Any]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Signal).where(
                Signal.status.in_(
                    [
                        "WON",
                        "LOST",
                    ]
                )
            )
        )
        signals = list(
            result.scalars().all()
        )
    total = len(signals)
    wins = sum(
        1
        for signal in signals
        if signal.status == "WON"
    )
    losses = sum(
        1
        for signal in signals
        if signal.status == "LOST"
    )
    if total:
        win_rate = (
            wins
            / total
            * 100.0
        )
    else:
        win_rate = 0.0
    scores = [
        signal.quality_score
        for signal in signals
        if signal.quality_score
        is not None
    ]
    average_score = (
        sum(scores) / len(scores)
        if scores
        else 0.0
    )
    return {
        "total": total,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "average_score": average_score,
    }
# ============================================================
# HELPERS
# ============================================================
def _parse_datetime(
    value: str,
) -> datetime:
    value = value.strip()
    # Поддержка:
    # 12:40 МСК
    # 12:40
    # ISO datetime
    # datetime string.
    if value.endswith("МСК"):
        value = value[:-3].strip()
        from time_utils import now_moscow
        now = now_moscow()
        hour, minute = map(
            int,
            value.split(":"),
        )
        return now.replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )
    try:
        return datetime.fromisoformat(
            value
        )
    except ValueError:
        from time_utils import now_moscow
        now = now_moscow()
        hour, minute = map(
            int,
            value.split(":"),
        )
        return now.replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )
