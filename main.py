from __future__ import annotations
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from fastapi import FastAPI
import uvicorn
from config import (
    BOT_TOKEN,
    HOST,
    PORT,
    validate_config,
)
from database import (
    close_database,
    init_database,
)
from market_factory import (
    create_market_client,
)
from scheduler import Scheduler
from handlers.start import router as start_router
from handlers.signals import router as signals_router
from handlers.applications import router as applications_router
from handlers.admin import router as admin_router
# ============================================================
# LOGGING
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(name)s | "
        "%(message)s"
    ),
)
logger = logging.getLogger("main")
# ============================================================
# RENDER PORT
# ============================================================
#
# Render Web Service передаёт порт через переменную окружения
# PORT.
#
# Например:
#
# PORT=10000
#
# Поэтому НЕ полагаемся только на PORT из config.py.
#
def get_render_port() -> int:
    raw_port = os.getenv("PORT")
    if raw_port is None:
        # Локальный запуск.
        try:
            return int(PORT)
        except (TypeError, ValueError):
            return 10000
    try:
        port = int(raw_port)
    except ValueError:
        logger.warning(
            "Invalid PORT environment variable: %r. "
            "Using 10000.",
            raw_port,
        )
        return 10000
    if not 1 <= port <= 65535:
        logger.warning(
            "PORT is outside valid range: %s. "
            "Using 10000.",
            port,
        )
        return 10000
    return port
RENDER_HOST = os.getenv(
    "HOST",
    HOST or "0.0.0.0",
)
RENDER_PORT = get_render_port()
logger.info(
    "HTTP server configuration: host=%s port=%s",
    RENDER_HOST,
    RENDER_PORT,
)
# ============================================================
# TELEGRAM BOT
# ============================================================
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(
        parse_mode=ParseMode.HTML,
    ),
)
# ============================================================
# DISPATCHER
# ============================================================
dp = Dispatcher()
# ============================================================
# ROUTERS
# ============================================================
_ROUTERS = (
    start_router,
    signals_router,
    applications_router,
    admin_router,
)
def register_routers() -> None:
    """
    Подключает все Telegram routers ровно один раз.
    """
    for router in _ROUTERS:
        if router.parent_router is not None:
            logger.warning(
                "Router '%s' is already attached to '%s'. "
                "Skipping duplicate registration.",
                router.name,
                router.parent_router,
            )
            continue
        dp.include_router(router)
        logger.info(
            "Router registered: %s",
            router.name,
        )
    logger.info(
        "All Telegram routers registered."
    )
# ============================================================
# REGISTER ROUTERS
# ============================================================
register_routers()
# ============================================================
# MARKET
# ============================================================
market = create_market_client()
# ============================================================
# SCHEDULER
# ============================================================
scheduler = Scheduler(
    bot=bot,
    market=market,
)
# ============================================================
# GLOBAL BOT TASK
# ============================================================
bot_task: asyncio.Task | None = None
# ============================================================
# TELEGRAM POLLING
# ============================================================
async def bot_polling() -> None:
    """
    Запускает Telegram long polling.
    """
    logger.info(
        "Telegram polling starting..."
    )
    try:
        await bot.delete_webhook(
            drop_pending_updates=True
        )
        logger.info(
            "Telegram webhook deleted."
        )
        logger.info(
            "Starting aiogram polling..."
        )
        await dp.start_polling(
            bot,
            allowed_updates=(
                dp.resolve_used_update_types()
            ),
        )
    except asyncio.CancelledError:
        logger.info(
            "Telegram polling cancelled."
        )
        raise
    except Exception:
        logger.exception(
            "Telegram polling crashed."
        )
        raise
# ============================================================
# FASTAPI LIFESPAN
# ============================================================
@asynccontextmanager
async def lifespan(
    app: FastAPI,
):
    global bot_task
    logger.info(
        "========================================"
    )
    logger.info(
        "TEYZUS starting..."
    )
    logger.info(
        "========================================"
    )
    # ========================================================
    # CONFIG
    # ========================================================
    logger.info(
        "Validating configuration..."
    )
    validate_config()
    logger.info(
        "Configuration valid."
    )
    # ========================================================
    # DATABASE
    # ========================================================
    logger.info(
        "Initializing database..."
    )
    await init_database()
    logger.info(
        "Database initialized."
    )
    # ========================================================
    # MARKET
    # ========================================================
    logger.info(
        "Starting market client..."
    )
    try:
        await market.start()
        logger.info(
            "Market client started."
        )
    except Exception:
        logger.exception(
            "Market client failed to start."
        )
        raise
    # ========================================================
    # SCHEDULER
    # ========================================================
    logger.info(
        "Starting scheduler..."
    )
    try:
        await scheduler.start()
        logger.info(
            "Scheduler started."
        )
        logger.info(
            "Automatic market signal scanning is managed "
            "by the scheduler."
        )
    except Exception:
        logger.exception(
            "Scheduler failed to start."
        )
        raise
    # ========================================================
    # TELEGRAM
    # ========================================================
    logger.info(
        "Starting Telegram bot..."
    )
    bot_task = asyncio.create_task(
        bot_polling(),
        name="teyzus_bot_polling",
    )
    logger.info(
        "Telegram bot task created."
    )
    # Небольшая пауза позволяет увидеть возможную ошибку
    # запуска polling в логах.
    await asyncio.sleep(0.2)
    logger.info(
        "========================================"
    )
    logger.info(
        "TEYZUS started successfully."
    )
    logger.info(
        "Telegram polling is running."
    )
    logger.info(
        "Automatic signal scanner is running "
        "through Scheduler."
    )
    logger.info(
        "HTTP server is running on %s:%s",
        RENDER_HOST,
        RENDER_PORT,
    )
    logger.info(
        "========================================"
    )
    try:
        yield
    finally:
        logger.info(
            "========================================"
        )
        logger.info(
            "TEYZUS shutting down..."
        )
        logger.info(
            "========================================"
        )
        # ====================================================
        # TELEGRAM
        # ====================================================
        if bot_task is not None:
            logger.info(
                "Stopping Telegram polling..."
            )
            if not bot_task.done():
                bot_task.cancel()
            try:
                await bot_task
            except asyncio.CancelledError:
                logger.info(
                    "Telegram polling stopped."
                )
            except Exception:
                logger.exception(
                    "Telegram polling shutdown error."
                )
        # ====================================================
        # SCHEDULER
        # ====================================================
        logger.info(
            "Stopping scheduler..."
        )
        try:
            await scheduler.stop()
            logger.info(
                "Scheduler stopped."
            )
        except Exception:
            logger.exception(
                "Scheduler shutdown error."
            )
        # ====================================================
        # MARKET
        # ====================================================
        logger.info(
            "Stopping market client..."
        )
        try:
            await market.close()
            logger.info(
                "Market client stopped."
            )
        except Exception:
            logger.exception(
                "Market client shutdown error."
            )
        # ====================================================
        # DATABASE
        # ====================================================
        logger.info(
            "Closing database..."
        )
        try:
            await close_database()
            logger.info(
                "Database closed."
            )
        except Exception:
            logger.exception(
                "Database shutdown error."
            )
        # ====================================================
        # BOT SESSION
        # ====================================================
        logger.info(
            "Closing Telegram bot session..."
        )
        try:
            await bot.session.close()
            logger.info(
                "Telegram bot session closed."
            )
        except Exception:
            logger.exception(
                "Telegram session shutdown error."
            )
        logger.info(
            "TEYZUS stopped."
        )
# ============================================================
# FASTAPI APP
# ============================================================
app = FastAPI(
    title="TEYZUS",
    description="TEYZUS market signal service",
    version="1.0.0",
    lifespan=lifespan,
)
# ============================================================
# ROOT
# ============================================================
@app.get("/")
async def root():
    telegram_status = (
        "running"
        if bot_task is not None
        and not bot_task.done()
        else "stopped"
    )
    return {
        "status": "ok",
        "service": "TEYZUS",
        "telegram": telegram_status,
        "host": RENDER_HOST,
        "port": RENDER_PORT,
    }
# ============================================================
# HEALTH
# ============================================================
@app.get("/health")
async def health():
    telegram_status = (
        "running"
        if bot_task is not None
        and not bot_task.done()
        else "stopped"
    )
    return {
        "status": "healthy",
        "service": "TEYZUS",
        "telegram": telegram_status,
        "host": RENDER_HOST,
        "port": RENDER_PORT,
    }
# ============================================================
# API STATUS
# ============================================================
@app.get("/api/status")
async def api_status():
    if bot_task is None:
        telegram_status = "not_started"
    elif bot_task.done():
        if bot_task.cancelled():
            telegram_status = "cancelled"
        elif bot_task.exception() is not None:
            telegram_status = "crashed"
        else:
            telegram_status = "stopped"
    else:
        telegram_status = "running"
    return {
        "status": "running",
        "service": "TEYZUS",
        "telegram": telegram_status,
        "host": RENDER_HOST,
        "port": RENDER_PORT,
    }
# ============================================================
# LOCAL / RENDER START
# ============================================================
if __name__ == "__main__":
    logger.info(
        "Starting Uvicorn..."
    )
    logger.info(
        "Binding HTTP server to %s:%s",
        RENDER_HOST,
        RENDER_PORT,
    )
    uvicorn.run(
        app,
        host=RENDER_HOST,
        port=RENDER_PORT,
        reload=False,
    )
