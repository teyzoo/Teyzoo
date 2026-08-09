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
)
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
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
# DATABASE URL
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
DATABASE_URL_ASYNC = (
    normalize_database_url(
        DATABASE_URL
    )
)
if not DATABASE_URL_ASYNC:
    raise RuntimeError(
        "DATABASE_URL не задан."
    )
# ============================================================
# ENGINE
# ============================================================
engine = create_async_engine(
    DATABASE_URL_ASYNC,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=1800,
)
SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
# ============================================================
# BASE
# ============================================================
class Base(
    AsyncAttrs,
    DeclarativeBase,
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
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
    symbol: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )
    direction: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
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
        String(16),
        nullable=True,
        index=True,
    )
    warning_sent: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    signal_sent: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    checked: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )
    entry_time: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime,
        nullable=True,
    )
    result_time: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime,
        nullable=True,
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
async def register_user(
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
        return result.scalar_one_or_none()
async def set_user_active(
    telegram_id: int,
    active: bool,
) -> None:
    async with SessionLocal() as session:
        result = await session.execute(
            select(User).where(
                User.telegram_id
                == telegram_id
            )
        )
        user = result.scalar_one_or_none()
        if user is None:
            return
        user.is_active = active
        user.updated_at = (
            datetime.utcnow()
        )
        await session.commit()
async def get_active_users() -> list[int]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(User.telegram_id).where(
                User.is_active.is_(True)
            )
        )
        return list(
            result.scalars().all()
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
) -> int:
    async with SessionLocal() as session:
        signal = Signal(
            symbol=symbol,
            direction=direction,
            score=float(score),
            close_time=close_time,
            historical_probability=(
                historical_probability
            ),
            warning_sent=False,
            signal_sent=False,
            checked=False,
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
# ============================================================
# SIGNAL HELPERS
# ============================================================
def signal_to_dict(
    signal: Signal,
) -> dict[str, Any]:
    return {
        "id": signal.id,
        "symbol": signal.symbol,
        "direction": signal.direction,
        "score": signal.score,
        "close_time": signal.close_time,
        "historical_probability": (
            signal.historical_probability
        ),
        "entry_price": signal.entry_price,
        "exit_price": signal.exit_price,
        "result": signal.result,
        "warning_sent": signal.warning_sent,
        "signal_sent": signal.signal_sent,
        "checked": signal.checked,
        "created_at": signal.created_at,
        "entry_time": signal.entry_time,
        "result_time": signal.result_time,
    }
# ============================================================
# PENDING SIGNALS
# ============================================================
async def get_pending_signals() -> list[dict[str, Any]]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Signal)
            .where(
                Signal.checked.is_(False)
            )
            .order_by(
                Signal.id.asc()
            )
        )
        signals = result.scalars().all()
        return [
            signal_to_dict(signal)
            for signal in signals
        ]
async def get_signal(
    signal_id: int,
) -> dict[str, Any] | None:
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
            return None
        return signal_to_dict(
            signal
        )
# ============================================================
# WARNING
# ============================================================
async def mark_warning_sent(
    signal_id: int,
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
        if signal.warning_sent:
            return False
        signal.warning_sent = True
        await session.commit()
        return True
# ============================================================
# SIGNAL SENT
# ============================================================
async def mark_signal_sent(
    signal_id: int,
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
        if signal.signal_sent:
            return False
        signal.signal_sent = True
        await session.commit()
        return True
# ============================================================
# ENTRY PRICE
# ============================================================
async def set_signal_entry_price(
    signal_id: int,
    entry_price: float,
    entry_time: datetime | None = None,
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
        signal.entry_time = (
            entry_time
            or datetime.utcnow()
        )
        await session.commit()
        return True
# ============================================================
# RESULT
# ============================================================
async def set_signal_result(
    signal_id: int,
    result_value: str,
    exit_price: float,
    result_time: datetime | None = None,
) -> bool:
    result_value = (
        result_value.upper().strip()
    )
    if result_value not in {
        "WIN",
        "LOSS",
        "DRAW",
    }:
        raise ValueError(
            "result_value должен быть "
            "WIN, LOSS или DRAW."
        )
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
        signal.result = result_value
        signal.exit_price = float(
            exit_price
        )
        signal.result_time = (
            result_time
            or datetime.utcnow()
        )
        signal.checked = True
        await session.commit()
        logger.info(
            "Signal #%s result: %s",
            signal_id,
            result_value,
        )
        return True
# ============================================================
# SIGNALS FOR RESULT CHECKER
# ============================================================
async def get_signals_for_result_check() -> list[dict[str, Any]]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Signal)
            .where(
                Signal.checked.is_(False),
                Signal.signal_sent.is_(True),
            )
            .order_by(
                Signal.id.asc()
            )
        )
        signals = result.scalars().all()
        return [
            signal_to_dict(signal)
            for signal in signals
        ]
# ============================================================
# SIGNALS FOR WARNING
# ============================================================
async def get_signals_for_warning() -> list[dict[str, Any]]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Signal)
            .where(
                Signal.warning_sent.is_(False),
                Signal.checked.is_(False),
            )
            .order_by(
                Signal.id.asc()
            )
        )
        signals = result.scalars().all()
        return [
            signal_to_dict(signal)
            for signal in signals
        ]
# ============================================================
# STATISTICS
# ============================================================
async def get_signal_statistics() -> dict[str, Any]:
    async with SessionLocal() as session:
        total_result = await session.execute(
            select(
                func.count(Signal.id)
            )
        )
        total = (
            total_result.scalar()
            or 0
        )
        wins_result = await session.execute(
            select(
                func.count(Signal.id)
            ).where(
                Signal.result == "WIN"
            )
        )
        wins = (
            wins_result.scalar()
            or 0
        )
        losses_result = await session.execute(
            select(
                func.count(Signal.id)
            ).where(
                Signal.result == "LOSS"
            )
        )
        losses = (
            losses_result.scalar()
            or 0
        )
        draws_result = await session.execute(
            select(
                func.count(Signal.id)
            ).where(
                Signal.result == "DRAW"
            )
        )
        draws = (
            draws_result.scalar()
            or 0
        )
        completed = (
            wins
            + losses
            + draws
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
            "draws": draws,
            "completed": completed,
            "win_rate": win_rate,
        }
# ============================================================
# CLOSE DATABASE
# ============================================================
async def close_db() -> None:
    await engine.dispose()
    logger.info(
        "Database connection closed."
    )

Это полная замена database.py.

После этого у нас база уже имеет весь необходимый фундамент для цепочки:

scheduler → предупреждение → сигнал → signal_result_checker → цена входа → цена выхода → WIN/LOSS → статистика.

Следующим файлом я бы поставил полный signal_result_checker.py, чтобы сразу состыковать его именно с этим database.py, а затем уже сделать финальный main.py.
