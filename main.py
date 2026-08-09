from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import (
    BOT_TOKEN,
    validate_config,
)

from database import (
    close_database,
    init_database,
)

from handlers import (
    admin,
    applications,
    signals,
    start,
)

from market_factory import (
    create_market_client,
)

from scheduler import (
    Scheduler,
)


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(name)s | "
        "%(message)s"
    ),
    stream=sys.stdout,
)

logger = logging.getLogger(
    "main"
)


# =========================================================
# GLOBAL OBJECTS
# =========================================================

bot: Bot | None = None
market = None
scheduler: Scheduler | None = None


# =========================================================
# DISPATCHER
# =========================================================

def create_dispatcher() -> Dispatcher:

    dp = Dispatcher()

    # -----------------------------------------------------
    # ROUTERS
    # -----------------------------------------------------

    dp.include_router(
        start.router
    )

    dp.include_router(
        signals.router
    )

    dp.include_router(
        applications.router
    )

    dp.include_router(
        admin.router
    )

    logger.info(
        "Telegram routers registered."
    )

    return dp


# =========================================================
# STARTUP
# =========================================================

async def startup(
    telegram_bot: Bot,
    market_client,
) -> Scheduler:

    global scheduler

    logger.info(
        "Starting TEYZUS..."
    )

    # -----------------------------------------------------
    # CONFIG
    # -----------------------------------------------------

    validate_config()

    logger.info(
        "Configuration validated."
    )

    # -----------------------------------------------------
    # DATABASE
    # -----------------------------------------------------

    await init_database()

    logger.info(
        "Database initialized."
    )

    # -----------------------------------------------------
    # MARKET
    # -----------------------------------------------------

    await market_client.start()

    logger.info(
        "Market client started."
    )

    # -----------------------------------------------------
    # SCHEDULER
    # -----------------------------------------------------

    scheduler = Scheduler(
        bot=telegram_bot,
        market=market_client,
    )

    await scheduler.start()

    logger.info(
        "Scheduler started."
    )

    logger.info(
        "TEYZUS startup completed."
    )

    return scheduler


# =========================================================
# SHUTDOWN
# =========================================================

async def shutdown(
    telegram_bot: Bot | None,
    market_client,
    current_scheduler: Scheduler | None,
) -> None:

    logger.info(
        "Starting TEYZUS shutdown..."
    )

    # -----------------------------------------------------
    # SCHEDULER
    # -----------------------------------------------------

    if current_scheduler is not None:

        try:

            await current_scheduler.stop()

        except Exception:

            logger.exception(
                "Failed to stop scheduler."
            )

    # -----------------------------------------------------
    # MARKET
    # -----------------------------------------------------

    if market_client is not None:

        try:

            await market_client.close()

        except Exception:

            logger.exception(
                "Failed to close market client."
            )

    # -----------------------------------------------------
    # DATABASE
    # -----------------------------------------------------

    try:

        await close_database()

    except Exception:

        logger.exception(
            "Failed to close database."
        )

    # -----------------------------------------------------
    # BOT SESSION
    # -----------------------------------------------------

    if telegram_bot is not None:

        try:

            await telegram_bot.session.close()

        except Exception:

            logger.exception(
                "Failed to close Telegram session."
            )

    logger.info(
        "TEYZUS shutdown completed."
    )


# =========================================================
# MAIN
# =========================================================

async def main() -> None:

    global bot
    global market
    global scheduler

    # -----------------------------------------------------
    # VALIDATE CONFIG BEFORE CREATING SERVICES
    # -----------------------------------------------------

    validate_config()

    logger.info(
        "Configuration is valid."
    )

    # -----------------------------------------------------
    # BOT
    # -----------------------------------------------------

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
        ),
    )

    logger.info(
        "Telegram bot object created."
    )

    # -----------------------------------------------------
    # DISPATCHER
    # -----------------------------------------------------

    dp = create_dispatcher()

    # -----------------------------------------------------
    # MARKET
    # -----------------------------------------------------

    market = create_market_client()

    logger.info(
        "Market client created."
    )

    # -----------------------------------------------------
    # START SERVICES
    # -----------------------------------------------------

    try:

        scheduler = await startup(
            telegram_bot=bot,
            market_client=market,
        )

        # -------------------------------------------------
        # REMOVE WEBHOOK
        # -------------------------------------------------

        await bot.delete_webhook(
            drop_pending_updates=False
        )

        logger.info(
            "Telegram webhook removed."
        )

        # -------------------------------------------------
        # BOT INFORMATION
        # -------------------------------------------------

        try:

            me = await bot.get_me()

            logger.info(
                "Telegram bot connected: @%s (%s)",
                me.username,
                me.id,
            )

        except Exception:

            logger.exception(
                "Could not retrieve Telegram bot info."
            )

        # -------------------------------------------------
        # POLLING
        # -------------------------------------------------

        logger.info(
            "Starting Telegram polling..."
        )

        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
        )

    except asyncio.CancelledError:

        logger.info(
            "Main task cancelled."
        )

        raise

    except KeyboardInterrupt:

        logger.info(
            "Keyboard interrupt received."
        )

    except Exception:

        logger.exception(
            "Fatal TEYZUS error."
        )

        raise

    finally:

        await shutdown(
            telegram_bot=bot,
            market_client=market,
            current_scheduler=scheduler,
        )

        bot = None
        market = None
        scheduler = None


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        logger.info(
            "TEYZUS stopped by user."
        )

    except Exception:

        logger.exception(
            "TEYZUS terminated with an error."
        )

        sys.exit(1)
