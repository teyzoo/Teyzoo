from __future__ import annotations
import asyncio
import logging
from aiogram import Bot
logger = logging.getLogger(
    "signal_notifications"
)
class SignalNotifier:
    """
    Единый модуль отправки уведомлений
    пользователям.
    Здесь специально нет прямого обращения
    к database.py, чтобы избежать циклических
    импортов.
    Список пользователей передаётся извне.
    """
    def __init__(
        self,
        bot: Bot,
    ):
        self.bot = bot
    async def send_to_user(
        self,
        telegram_id: int,
        text: str,
    ) -> bool:
        try:
            await self.bot.send_message(
                chat_id=telegram_id,
                text=text,
                parse_mode="HTML",
            )
            return True
        except Exception as exc:
            logger.warning(
                "Failed to send message "
                "to %s: %s",
                telegram_id,
                exc,
            )
            return False
    async def send_to_users(
        self,
        telegram_ids: list[int],
        text: str,
    ) -> int:
        if not telegram_ids:
            return 0
        sent = 0
        for telegram_id in telegram_ids:
            success = await self.send_to_user(
                telegram_id=telegram_id,
                text=text,
            )
            if success:
                sent += 1
            # Небольшая пауза между отправками,
            # чтобы не создавать резкий burst.
            await asyncio.sleep(0.03)
        logger.info(
            "Notification sent to %s/%s users.",
            sent,
            len(telegram_ids),
        )
        return sent
    async def send_warning(
        self,
        telegram_ids: list[int],
        text: str,
    ) -> int:
        return await self.send_to_users(
            telegram_ids=telegram_ids,
            text=text,
        )
    async def send_signal(
        self,
        telegram_ids: list[int],
        text: str,
    ) -> int:
        return await self.send_to_users(
            telegram_ids=telegram_ids,
            text=text,
        )
    async def send_result(
        self,
        telegram_ids: list[int],
        text: str,
    ) -> int:
        return await self.send_to_users(
            telegram_ids=telegram_ids,
            text=text,
        )
