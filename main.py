from __future__ import annotations
import asyncio
import logging
import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import (
    DefaultBotProperties,
)
from aiogram.enums import ParseMode
from fastapi import FastAPI
from config import (
    BOT_TOKEN,
    HOST,
    PORT,
    validate_config,
)
from database import (
    close_db,
    init_db,
)
from handlers.admin import (
    router as admin_router,
)
from handlers.applications import (
    router as applications_router,
)
from handlers.signals import (
    router as signals_router,
)
from handlers.start import (
    router as start_router,
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
# BOT
# ============================================================
async def run_bot():
    logger.info(
        "Starting Telegram bot..."
    )
    validate_config()
    await init_db()
    market_client = (
        create_market_client()
    )
    await market_client.start()
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
        ),
    )
    dp = Dispatcher()
    # ========================================================
    # ROUTERS
    # ========================================================
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
    # ========================================================
    # BACKGROUND TASKS
    # ========================================================
    scheduler_task = asyncio.create_task(
        signal_scheduler(
            bot=bot,
            market=market_client,
        )
    )
    result_checker_task = asyncio.create_task(
        signal_result_checker(
            bot=bot,
            market=market_client,
        )
    )
    logger.info(
        "Background tasks started."
    )
    try:
        # Удаляем webhook перед polling,
        # чтобы не было TelegramConflictError.
        await bot.delete_webhook(
            drop_pending_updates=True
        )
        logger.info(
            "Telegram polling started."
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
        # ====================================================
        # STOP SCHEDULER
        # ====================================================
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
        # ====================================================
        # STOP RESULT CHECKER
        # ====================================================
        result_checker_task.cancel()
        try:
            await result_checker_task
        except asyncio.CancelledError:
            pass
        # ====================================================
        # CLOSE MARKET
        # ====================================================
        try:
            await market_client.close()
        except Exception:
            logger.exception(
                "Error closing market client."
            )
        # ====================================================
        # CLOSE BOT
        # ====================================================
        try:
            await bot.session.close()
        except Exception:
            logger.exception(
                "Error closing Telegram session."
            )
        # ====================================================
        # CLOSE DATABASE
        # ====================================================
        try:
            await close_db()
        except Exception:
            logger.exception(
                "Error closing database."
            )
        logger.info(
            "Bot shutdown completed."
        )
# ============================================================
# APPLICATION
# ============================================================
async def main():
    logger.info(
        "===================================="
    )
    logger.info(
        "TEYZUS SIGNAL BOT STARTING"
    )
    logger.info(
        "===================================="
    )
    bot_task = asyncio.create_task(
        run_bot()
    )
    uvicorn_config = uvicorn.Config(
        app=app,
        host=HOST,
        port=PORT,
        log_level="info",
    )
    server = uvicorn.Server(
        uvicorn_config
    )
    try:
        await server.serve()
    except asyncio.CancelledError:
        raise
    finally:
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
                "Bot shutdown error."
            )
# ============================================================
# ENTRY POINT
# ============================================================
if __name__ == "__main__":
    try:
        asyncio.run(
            main()
        )
    except KeyboardInterrupt:
        logger.info(
            "Application stopped."
        )
