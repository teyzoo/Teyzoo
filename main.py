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
#
# ВАЖНО:
# Каждый router подключается только здесь.
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

        # Если router уже подключён,
        # повторно его не подключаем.
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

        # Удаляем webhook перед polling.
        #
        # Это важно, если раньше бот работал
        # через webhook.
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

    # Небольшая пауза позволяет увидеть ошибки
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
    return {
        "status": "ok",
        "service": "TEYZUS",
        "telegram": (
            "running"
            if bot_task is not None
            and not bot_task.done()
            else "stopped"
        ),
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
    }


# ============================================================
# LOCAL START
# ============================================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        reload=False,
    )
