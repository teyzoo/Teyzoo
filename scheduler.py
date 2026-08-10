from __future__ import annotations
import asyncio
import logging
from aiogram import Bot
from config import (
    OWNER_ID,
    SIGNAL_SCAN_INTERVAL,
    SIGNAL_MINIMUM_QUALITY,
)
from market import MarketClient
from result_checker import (
    result_checker_loop,
)
from signal_warning.scheduler import (
    warning_scheduler,
)
from signal_scanner import (
    SignalScanner,
    TradingSignal,
)
logger = logging.getLogger("scheduler")
# =========================================================
# SIGNAL SCANNER CALLBACK
# =========================================================
async def send_scanner_signal(
    bot: Bot,
    signal: TradingSignal,
) -> None:
    """
    Отправляет автоматически найденный сигнал
    владельцу бота.
    Сигнал приходит без необходимости нажимать
    кнопку "Получить сигнал".
    """
    if OWNER_ID <= 0:
        logger.error(
            "OWNER_ID is not configured. "
            "Cannot send automatic signal."
        )
        return
    text = SignalScanner.format_signal(
        signal
    )
    try:
        await bot.send_message(
            chat_id=OWNER_ID,
            text=text,
        )
        logger.info(
            (
                "Automatic signal sent | "
                "symbol=%s | "
                "direction=%s | "
                "quality=%.2f"
            ),
            signal.symbol,
            signal.direction,
            signal.quality_score,
        )
    except Exception:
        logger.exception(
            (
                "Failed to send automatic "
                "signal | symbol=%s"
            ),
            signal.symbol,
        )
# =========================================================
# SCHEDULER
# =========================================================
class Scheduler:
    """
    Главный планировщик TEYZUS.
    Запускает:
        1. SignalScanner
           Автоматический поиск сигналов.
        2. warning_scheduler
           Предупреждения по сигналам.
        3. result_checker_loop
           Проверку результатов сигналов.
    Старый signal_generation_loop здесь НЕ используется.
    SignalScanner самостоятельно:
        - получает пары;
        - получает свечи;
        - анализирует таймфреймы;
        - применяет QualityFilter;
        - формирует TradingSignal;
        - отправляет его через callback.
    """
    def __init__(
        self,
        bot: Bot,
        market: MarketClient,
    ) -> None:
        self.bot = bot
        self.market = market
        # -------------------------------------------------
        # TASKS
        # -------------------------------------------------
        self.tasks: list[
            asyncio.Task
        ] = []
        # -------------------------------------------------
        # SCANNER
        # -------------------------------------------------
        self.scanner: SignalScanner | None = None
        # -------------------------------------------------
        # STATE
        # -------------------------------------------------
        self._started = False
    # =====================================================
    # CREATE SCANNER
    # =====================================================
    def _create_scanner(
        self,
    ) -> SignalScanner:
        """
        Создаёт автоматический SignalScanner.
        Основные настройки берутся из config.py /
        Environment Variables.
        Важный момент:
            SIGNAL_SCAN_INTERVAL
        должен быть:
            300
        чтобы полный цикл запускался каждые 5 минут.
        """
        async def callback(
            signal: TradingSignal,
        ) -> None:
            await send_scanner_signal(
                self.bot,
                signal,
            )
        scanner = SignalScanner(
            market_client=self.market,
            send_signal=callback,
            # -------------------------------------------------
            # 5 MINUTES
            # -------------------------------------------------
            scan_interval=max(
                300,
                int(
                    SIGNAL_SCAN_INTERVAL
                ),
            ),
            # -------------------------------------------------
            # QUALITY
            # -------------------------------------------------
            minimum_quality=float(
                SIGNAL_MINIMUM_QUALITY
            ),
        )
        logger.info(
            (
                "SignalScanner created | "
                "pairs=%s | "
                "timeframes=%s | "
                "interval=%ss | "
                "minimum_quality=%.1f"
            ),
            len(
                scanner.get_symbols()
            ),
            scanner.timeframes,
            scanner.scan_interval,
            scanner.minimum_quality,
        )
        logger.info(
            "Scanner pairs:"
        )
        for symbol in scanner.get_symbols():
            logger.info(
                " - %s",
                symbol,
            )
        return scanner
    # =====================================================
    # START
    # =====================================================
    async def start(
        self,
    ) -> None:
        """
        Запускает Scheduler.
        Защита от повторного запуска включена.
        """
        # -------------------------------------------------
        # ALREADY STARTED
        # -------------------------------------------------
        if self._started:
            logger.warning(
                "Scheduler already started."
            )
            return
        # -------------------------------------------------
        # OLD ACTIVE TASKS
        # -------------------------------------------------
        active_tasks = [
            task
            for task in self.tasks
            if not task.done()
        ]
        if active_tasks:
            logger.warning(
                (
                    "Scheduler already has "
                    "%s active tasks."
                ),
                len(active_tasks),
            )
            return
        # -------------------------------------------------
        # RESET
        # -------------------------------------------------
        self.tasks.clear()
        logger.info(
            "========================================"
        )
        logger.info(
            "Starting TEYZUS scheduler..."
        )
        logger.info(
            "========================================"
        )
        # =================================================
        # SIGNAL SCANNER
        # =================================================
        logger.info(
            "Creating automatic SignalScanner..."
        )
        try:
            self.scanner = (
                self._create_scanner()
            )
        except Exception:
            logger.exception(
                "Failed to create SignalScanner."
            )
            raise
        # -------------------------------------------------
        # START SCANNER
        # -------------------------------------------------
        logger.info(
            "Starting automatic signal scanner..."
        )
        try:
            await self.scanner.start()
        except Exception:
            logger.exception(
                "Failed to start SignalScanner."
            )
            self.scanner = None
            raise
        logger.info(
            "Automatic SignalScanner started."
        )
        # =================================================
        # WARNING SCHEDULER
        # =================================================
        logger.info(
            "Starting signal warning scheduler..."
        )
        warning_task = asyncio.create_task(
            warning_scheduler(
                self.bot
            ),
            name="signal_warning",
        )
        # =================================================
        # RESULT CHECKER
        # =================================================
        logger.info(
            "Starting signal result checker..."
        )
        result_task = asyncio.create_task(
            result_checker_loop(
                self.bot,
                self.market,
            ),
            name="signal_result_checker",
        )
        # =================================================
        # SAVE TASKS
        # =================================================
        self.tasks = [
            warning_task,
            result_task,
        ]
        self._started = True
        # =================================================
        # LOG
        # =================================================
        logger.info(
            "========================================"
        )
        logger.info(
            "TEYZUS scheduler started successfully."
        )
        logger.info(
            "Automatic signal scanner: RUNNING"
        )
        logger.info(
            (
                "Automatic scan interval: %s seconds "
                "(%s minutes)"
            ),
            self.scanner.scan_interval,
            self.scanner.scan_interval / 60,
        )
        logger.info(
            (
                "Signal quality threshold: %.1f%%"
            ),
            self.scanner.minimum_quality,
        )
        logger.info(
            (
                "Scanner pairs: %s"
            ),
            len(
                self.scanner.get_symbols()
            ),
        )
        logger.info(
            (
                "Scanner timeframes: %s"
            ),
            self.scanner.timeframes,
        )
        logger.info(
            "========================================"
        )
        logger.info(
            "Scheduler background tasks:"
        )
        logger.info(
            " - SignalScanner"
        )
        logger.info(
            " - signal_warning"
        )
        logger.info(
            " - signal_result_checker"
        )
    # =====================================================
    # STOP
    # =====================================================
    async def stop(
        self,
    ) -> None:
        """
        Полностью останавливает scheduler.
        """
        if (
            not self._started
            and self.scanner is None
            and not self.tasks
        ):
            return
        logger.info(
            "========================================"
        )
        logger.info(
            "Stopping TEYZUS scheduler..."
        )
        logger.info(
            "========================================"
        )
        # =================================================
        # STOP SIGNAL SCANNER
        # =================================================
        if self.scanner is not None:
            logger.info(
                "Stopping automatic SignalScanner..."
            )
            try:
                await self.scanner.stop()
                logger.info(
                    "SignalScanner stopped."
                )
            except Exception:
                logger.exception(
                    "SignalScanner shutdown error."
                )
            finally:
                self.scanner = None
        # =================================================
        # STOP OTHER TASKS
        # =================================================
        if self.tasks:
            logger.info(
                (
                    "Stopping %s scheduler tasks..."
                ),
                len(self.tasks),
            )
            # -------------------------------------------------
            # CANCEL
            # -------------------------------------------------
            for task in self.tasks:
                if not task.done():
                    logger.info(
                        "Cancelling task: %s",
                        task.get_name(),
                    )
                    task.cancel()
            # -------------------------------------------------
            # WAIT
            # -------------------------------------------------
            results = await asyncio.gather(
                *self.tasks,
                return_exceptions=True,
            )
            # -------------------------------------------------
            # RESULTS
            # -------------------------------------------------
            for task, result in zip(
                self.tasks,
                results,
            ):
                if isinstance(
                    result,
                    asyncio.CancelledError,
                ):
                    logger.info(
                        "Task cancelled: %s",
                        task.get_name(),
                    )
                    continue
                if isinstance(
                    result,
                    Exception,
                ):
                    logger.error(
                        (
                            "Task %s stopped "
                            "with error: %s"
                        ),
                        task.get_name(),
                        result,
                    )
                else:
                    logger.info(
                        "Task stopped: %s",
                        task.get_name(),
                    )
        # -------------------------------------------------
        # CLEAR
        # -------------------------------------------------
        self.tasks.clear()
        self._started = False
        logger.info(
            "========================================"
        )
        logger.info(
            "TEYZUS scheduler stopped."
        )
        logger.info(
            "========================================"
        )
    # =====================================================
    # STATUS
    # =====================================================
    @property
    def running(
        self,
    ) -> bool:
        return self._started
    # =====================================================
    # SCANNER STATUS
    # =====================================================
    @property
    def scanner_running(
        self,
    ) -> bool:
        return (
            self.scanner is not None
            and self.scanner.running
        )
    # =====================================================
    # SCANNER STATS
    # =====================================================
    def get_scanner_stats(
        self,
    ):
        """
        Возвращает статистику SignalScanner.
        Если scanner ещё не запущен,
        возвращается None.
        """
        if self.scanner is None:
            return None
        return self.scanner.get_stats()
# =========================================================
# PUBLIC API
# =========================================================
__all__ = [
    "Scheduler",
    "send_scanner_signal",
]
