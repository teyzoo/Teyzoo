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
from market_factory import (
    create_market_client,
)
from scheduler import (
    Scheduler,
)
from handlers.start import router as start_router
from handlers.signals import router as signals_router
from handlers.applications import (
    router as applications_router,
)
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
# ------------------------------------------------------------
# ROUTERS
# ------------------------------------------------------------
# Каждый router подключается РОВНО ОДИН РАЗ.
dp.include_router(start_router)
dp.include_router(signals_router)
dp.include_router(applications_router)
dp.include_router(admin_router)
logger.info(
    "All Telegram routers registered."
)
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
# GLOBAL TASK
# ============================================================
bot_task: asyncio.Task | None = None
# ============================================================
# TELEGRAM POLLING
# ============================================================
async def bot_polling() -> None:
    """
    Запускает Telegram polling.
    Polling работает как отдельная asyncio-задача
    внутри FastAPI lifespan.
    """
    logger.info(
        "Telegram polling starting..."
    )
    try:
        # На Render Telegram webhook нам не нужен.
        # Удаляем webhook перед запуском polling.
        await bot.delete_webhook(
            drop_pending_updates=True,
        )
        logger.info(
            "Telegram webhook deleted."
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
    """
    Полный жизненный цикл TEYZUS.
    Startup:
        1. Проверка конфигурации
        2. База данных
        3. Market client
        4. Scheduler
        5. Telegram polling
    Shutdown:
        1. Telegram
        2. Scheduler
        3. Market
        4. Database
    """
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
        "Configuration validated."
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
        "Telegram bot task created."
    )
    logger.info(
        "================================"
    )
    logger.info(
        "TEYZUS started successfully."
    )
    logger.info(
        "================================"
    )
    # ========================================================
    # APPLICATION RUNNING
    # ========================================================
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
                logger.info(
                    "Telegram bot stopped."
                )
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
        # FINISHED
        # ====================================================
        logger.info(
            "================================"
        )
        logger.info(
            "TEYZUS stopped."
        )
        logger.info(
            "================================"
        )
# ============================================================
# FASTAPI APPLICATION
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
# LOCAL / RENDER START
# ============================================================
if __name__ == "__main__":
    import uvicorn
    logger.info(
        "Starting Uvicorn..."
    )
    # ВАЖНО:
    #
    # НЕ:
    #
    # uvicorn.run(
    #     "main:app",
    #     ...
    # )
    #
    # Потому что Render запускает:
    #
    # python main.py
    #
    # А строка "main:app" заставляет Uvicorn
    # импортировать main.py повторно.
    #
    # Это приводит к повторному подключению
    # Telegram routers и ошибке:
    #
    # RuntimeError:
    # Router is already attached to Dispatcher
    #
    # Поэтому передаём уже существующий объект app.
    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        reload=False,
    )
