from __future__ import annotations
import asyncio
import logging
from contextlib import asynccontextmanager
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from fastapi import FastAPI
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
from market_factory import create_market_client
from scheduler import Scheduler
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
# BOT
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
def register_routers() -> None:
    """
    Регистрирует Telegram routers ровно один раз.
    ВАЖНО:
    Не подключаем routers напрямую в нескольких местах.
    """
    from handlers.start import router as start_router
    from handlers.signals import router as signals_router
    from handlers.applications import router as applications_router
    from handlers.admin import router as admin_router
    routers = [
        start_router,
        signals_router,
        applications_router,
        admin_router,
    ]
    for router in routers:
        # Если router уже находится внутри этого Dispatcher,
        # повторно подключать его нельзя.
        if router.parent_router is None:
            dp.include_router(router)
    logger.info(
        "All Telegram routers registered."
    )
# Регистрируем routers один раз.
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
# BOT TASK
# ============================================================
bot_task: asyncio.Task | None = None
# ============================================================
# TELEGRAM POLLING
# ============================================================
async def bot_polling() -> None:
    """
    Запускает Telegram polling.
    """
    logger.info(
        "Telegram polling starting..."
    )
    try:
        await bot.delete_webhook(
            drop_pending_updates=True,
        )
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
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
        "================================"
    )
    logger.info(
        "TEYZUS starting..."
    )
    logger.info(
        "================================"
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
    await market.start()
    logger.info(
        "Market client started."
    )
    # ========================================================
    # SCHEDULER
    # ========================================================
    logger.info(
        "Starting scheduler..."
    )
    await scheduler.start()
    logger.info(
        "Scheduler started."
    )
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
        "TEYZUS started successfully."
    )
    try:
        yield
    finally:
        logger.info(
            "================================"
        )
        logger.info(
            "TEYZUS shutting down..."
        )
        logger.info(
            "================================"
        )
        # ====================================================
        # TELEGRAM
        # ====================================================
        if bot_task is not None:
            logger.info(
                "Stopping Telegram bot..."
            )
            bot_task.cancel()
            try:
                await bot_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception(
                    "Telegram bot shutdown error."
                )
        # ====================================================
        # SCHEDULER
        # ====================================================
        logger.info(
            "Stopping scheduler..."
        )
        try:
            await scheduler.stop()
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
        except Exception:
            logger.exception(
                "Telegram bot session shutdown error."
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
    return {
        "status": "ok",
        "service": "TEYZUS",
    }
# ============================================================
# HEALTH
# ============================================================
@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "TEYZUS",
    }
# ============================================================
# API STATUS
# ============================================================
@app.get("/api/status")
async def api_status():
    telegram_status = (
        "stopped"
        if bot_task is None
        else (
            "running"
            if not bot_task.done()
            else "stopped"
        )
    )
    return {
        "status": "running",
        "service": "TEYZUS",
        "telegram": telegram_status,
    }
# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        reload=False,
    )
