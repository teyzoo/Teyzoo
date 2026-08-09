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


app = FastAPI(
    title="TEYZUS Signal Bot",
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


async def run_bot():

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

    scheduler_task = asyncio.create_task(
        signal_scheduler(
            bot,
            market_client,
        )
    )

    try:

        logger.info(
            "TEYZUS Signal Bot запускается..."
        )

        await bot.delete_webhook(
            drop_pending_updates=True
        )

        logger.info(
            "Telegram polling запущен."
        )

        await dp.start_polling(
            bot
        )

    finally:

        scheduler_task.cancel()

        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass

        await market_client.close()

        await bot.session.close()

        await close_db()


async def main():

    bot_task = asyncio.create_task(
        run_bot()
    )

    config = uvicorn.Config(
        app,
        host=HOST,
        port=PORT,
        log_level="info",
    )

    server = uvicorn.Server(
        config
    )

    try:

        await server.serve()

    finally:

        bot_task.cancel()

        try:
            await bot_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(main())
