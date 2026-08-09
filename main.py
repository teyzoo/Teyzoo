import asyncio
import logging

import uvicorn

from fastapi import FastAPI

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

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

from market_factory import create_market_client

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

logger = logging.getLogger(
    "teyzus"
)


app = FastAPI(
    title="TEYZUS Signal Bot",
)


market_client = create_market_client()


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

    logger.info(
        "Database initialized."
    )

    await market_client.start()

    logger.info(
        "Market client started."
    )

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
            bot=bot,
            market=market_client,
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

    except Exception:

        logger.exception(
            "Ошибка Telegram bot."
        )

        raise

    finally:

        logger.info(
            "Останавливаем scheduler..."
        )

        scheduler_task.cancel()

        try:

            await scheduler_task

        except asyncio.CancelledError:

            pass

        logger.info(
            "Закрываем market client..."
        )

        await market_client.close()

        logger.info(
            "Закрываем Telegram bot..."
        )

        await bot.session.close()

        logger.info(
            "Bot shutdown completed."
        )


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

        logger.info(
            "FastAPI запускается "
            "на %s:%s",
            HOST,
            PORT,
        )

        await server.serve()

    finally:

        if not bot_task.done():

            bot_task.cancel()

        try:

            await bot_task

        except asyncio.CancelledError:

            pass

        except Exception:

            logger.exception(
                "Ошибка при остановке bot task."
            )


if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        logger.info(
            "TEYZUS остановлен."
        )
