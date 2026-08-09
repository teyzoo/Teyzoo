from __future__ import annotations
import asyncio
import logging
import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from fastapi import FastAPI
from config import (
    BOT_TOKEN,
    HOST,
    PORT,
)
from database import (
    init_db,
)
from handlers.start import (
    router as start_router,
)
from handlers.signals import (
    router as signals_router,
)
from handlers.applications import (
    router as applications_router,
)
from handlers.admin import (
    router as admin_router,
)
from market_factory import (
    create_market_client,
)
from scheduler import (
    signal_scheduler,
)
from signal_result_checker import (
    signal_result_checker,
)
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
logger = logging.getLogger(
    "teyzus"
)
# ============================================================
# FASTAPI
# ============================================================
app = FastAPI(
    title="TEYZUS Signal Bot",
    version="1.0.0",
)
@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "TEYZUS Signal Bot",
    }
@app.get("/health")
async def health():
    return {
        "status": "healthy",
    }
# ============================================================
# MARKET CLIENT
# ============================================================
market_client = create_market_client()
# ============================================================
# BOT
# ============================================================
async def run_bot():
    """
    Запускает Telegram-бота,
    scheduler и автоматическую
    проверку результатов.
    """
    logger.info(
        "Initializing database..."
    )
    await init_db()
    logger.info(
        "Database initialized."
    )
    # --------------------------------------------------------
    # MARKET
    # --------------------------------------------------------
    logger.info(
        "Starting market client..."
    )
    await market_client.start()
    logger.info(
        "Market client started."
    )
    # --------------------------------------------------------
    # BOT
    # --------------------------------------------------------
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
        ),
    )
    dp = Dispatcher()
    # --------------------------------------------------------
    # ROUTERS
    # --------------------------------------------------------
    dp.include_router(
        start_router
    )
    dp.include_router(
        signals_router
    )
    dp.include_router(
        applications_router
    )
    dp.include_router(
        admin_router
    )
    logger.info(
        "Telegram routers loaded."
    )
    # --------------------------------------------------------
    # SIGNAL SCHEDULER
    # --------------------------------------------------------
    scheduler_task = asyncio.create_task(
        signal_scheduler(
            bot=bot,
            market=market_client,
        )
    )
    logger.info(
        "Signal scheduler task started."
    )
    # --------------------------------------------------------
    # RESULT CHECKER
    # --------------------------------------------------------
    result_checker_task = asyncio.create_task(
        signal_result_checker(
            bot=bot,
            market=market_client,
        )
    )
    logger.info(
        "Signal result checker task started."
    )
    # --------------------------------------------------------
    # TELEGRAM POLLING
    # --------------------------------------------------------
    try:
        logger.info(
            "===================================="
        )
        logger.info(
            "TEYZUS Signal Bot запускается..."
        )
        logger.info(
            "Telegram polling starting..."
        )
        # Удаляем старый webhook,
        # чтобы polling не конфликтовал
        # с предыдущим запуском.
        await bot.delete_webhook(
            drop_pending_updates=True
        )
        logger.info(
            "Webhook removed."
        )
        logger.info(
            "Telegram polling запущен."
        )
        await dp.start_polling(
            bot
        )
    except asyncio.CancelledError:
        logger.info(
            "Bot task cancelled."
        )
        raise
    except Exception:
        logger.exception(
            "Telegram bot crashed."
        )
        raise
    finally:
        # ----------------------------------------------------
        # STOP SCHEDULER
        # ----------------------------------------------------
        logger.info(
            "Stopping signal scheduler..."
        )
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
        # ----------------------------------------------------
        # STOP RESULT CHECKER
        # ----------------------------------------------------
        logger.info(
            "Stopping signal result checker..."
        )
        result_checker_task.cancel()
        try:
            await result_checker_task
        except asyncio.CancelledError:
            pass
        # ----------------------------------------------------
        # MARKET
        # ----------------------------------------------------
        logger.info(
            "Closing market client..."
        )
        try:
            await market_client.close()
        except Exception:
            logger.exception(
                "Could not close market client."
            )
        # ----------------------------------------------------
        # BOT SESSION
        # ----------------------------------------------------
        logger.info(
            "Closing Telegram bot session..."
        )
        try:
            await bot.session.close()
        except Exception:
            logger.exception(
                "Could not close Telegram session."
            )
        logger.info(
            "TEYZUS bot stopped."
        )
# ============================================================
# APPLICATION ENTRYPOINT
# ============================================================
async def main():
    """
    Одновременно запускает:
    1. FastAPI
    2. Telegram Bot
    3. Signal Scheduler
    4. Signal Result Checker
    """
    logger.info(
        "Starting TEYZUS application..."
    )
    bot_task = asyncio.create_task(
        run_bot()
    )
    # --------------------------------------------------------
    # UVICORN
    # --------------------------------------------------------
    uvicorn_config = uvicorn.Config(
        app=app,
        host=HOST,
        port=PORT,
        log_level="info",
    )
    server = uvicorn.Server(
        uvicorn_config
    )
    logger.info(
        "Starting FastAPI server on %s:%s",
        HOST,
        PORT,
    )
    try:
        await server.serve()
    except asyncio.CancelledError:
        logger.info(
            "FastAPI server cancelled."
        )
        raise
    except Exception:
        logger.exception(
            "FastAPI server crashed."
        )
        raise
    finally:
        logger.info(
            "Stopping Telegram bot task..."
        )
        bot_task.cancel()
        try:
            await bot_task
        except asyncio.CancelledError:
            pass
        logger.info(
            "TEYZUS application stopped."
        )
# ============================================================
# START
# ============================================================
if __name__ == "__main__":
    try:
        asyncio.run(
            main()
        )
    except KeyboardInterrupt:
        logger.info(
            "Application interrupted."
        )
