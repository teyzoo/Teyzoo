import asyncio
import logging

from fastapi import FastAPI
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

import uvicorn

from config import (
    BOT_TOKEN,
    HOST,
    PORT,
)

from database import init_db

from handlers.start import router as start_router
from handlers.signals import router as signals_router
from handlers.applications import router as applications_router
from handlers.admin import router as admin_router

from market import market_client

from scheduler import signal_scheduler


logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(name)s | "
        "%(message)s"
    ),
)

logger = logging.getLogger("teyzus")


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

    await init_db()

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
        signal_scheduler(bot)
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

        await dp.start_polling(bot)

    finally:

        scheduler_task.cancel()

        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass

        await market_client.close()

        await bot.session.close()


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
