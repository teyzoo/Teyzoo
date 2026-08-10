Полный scheduler.py:

from __future__ import annotations
import asyncio
import importlib
import inspect
import logging
from typing import Any
from aiogram import Bot
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
from config import (
    OWNER_ID,
)
logger = logging.getLogger(
    "scheduler"
)
# =========================================================
# SIGNAL GENERATOR DISCOVERY
# =========================================================
GENERATOR_MODULES = (
    "signal_generator",
    "signal_engine",
    "signal_analyzer",
    "analyzer",
    "signals.generator",
    "signals.engine",
    "signals.analyzer",
)
GENERATOR_FUNCTIONS = (
    "generate_signal",
    "generate_signals",
    "analyze_market",
    "analyze_markets",
    "find_signal",
    "find_signals",
    "run_signal_analysis",
    "run_analysis",
)
# =========================================================
# LOAD SIGNAL GENERATOR
# =========================================================
def _load_generator(
    market: MarketClient,
) -> Any | None:
    """
    Ищет существующий движок генерации сигналов.
    Поддерживает:
    1. Обычные функции:
       generate_signal()
       generate_signals()
       analyze_market()
       ...
    2. Класс:
       SignalGenerator(market)
       с методом:
       generate(bot)
    """
    for module_name in GENERATOR_MODULES:
        try:
            module = importlib.import_module(
                module_name
            )
        except ModuleNotFoundError:
            continue
        except Exception:
            logger.exception(
                "Failed to import signal module: %s",
                module_name,
            )
            continue
        # =================================================
        # ВАРИАНТ 1
        # ОБЫЧНАЯ ФУНКЦИЯ
        # =================================================
        for function_name in GENERATOR_FUNCTIONS:
            function = getattr(
                module,
                function_name,
                None,
            )
            if function is None:
                continue
            if not callable(function):
                continue
            logger.info(
                "Signal generator function found: "
                "%s.%s",
                module_name,
                function_name,
            )
            return function
        # =================================================
        # ВАРИАНТ 2
        # SIGNAL GENERATOR
        # =================================================
        generator_class = getattr(
            module,
            "SignalGenerator",
            None,
        )
        if generator_class is None:
            continue
        logger.info(
            "SignalGenerator class found in %s",
            module_name,
        )
        # -------------------------------------------------
        # СОЗДАЁМ ЭКЗЕМПЛЯР
        # -------------------------------------------------
        try:
            instance = generator_class(
                market
            )
        except TypeError:
            try:
                instance = generator_class(
                    market=market
                )
            except Exception:
                logger.exception(
                    "Failed to initialize "
                    "SignalGenerator from %s",
                    module_name,
                )
                continue
        except Exception:
            logger.exception(
                "Failed to initialize "
                "SignalGenerator from %s",
                module_name,
            )
            continue
        # -------------------------------------------------
        # ИЩЕМ GENERATE
        # -------------------------------------------------
        generate_method = getattr(
            instance,
            "generate",
            None,
        )
        if callable(generate_method):
            logger.info(
                "Signal generator connected: "
                "%s.SignalGenerator.generate",
                module_name,
            )
            return generate_method
        # -------------------------------------------------
        # ДОПОЛНИТЕЛЬНЫЕ МЕТОДЫ
        # -------------------------------------------------
        for method_name in GENERATOR_FUNCTIONS:
            method = getattr(
                instance,
                method_name,
                None,
            )
            if callable(method):
                logger.info(
                    "Signal generator method found: "
                    "%s.SignalGenerator.%s",
                    module_name,
                    method_name,
                )
                return method
    return None
# =========================================================
# GET ANALYSIS INTERVAL
# =========================================================
def _get_analysis_interval() -> int:
    """
    Старый цикл генератора.
    Оставлен специально, чтобы не удалить
    существующий функционал проекта.
    Основная переменная:
        SIGNAL_ANALYSIS_INTERVAL
    По умолчанию:
        20 секунд
    """
    try:
        from config import (
            SIGNAL_ANALYSIS_INTERVAL,
        )
        interval = int(
            SIGNAL_ANALYSIS_INTERVAL
        )
        return max(
            1,
            interval,
        )
    except Exception:
        logger.warning(
            "SIGNAL_ANALYSIS_INTERVAL "
            "is unavailable. "
            "Using 20 seconds."
        )
        return 20
# =========================================================
# CALL GENERATOR
# =========================================================
async def _call_generator(
    generator: Any,
    bot: Bot,
    market: MarketClient,
) -> Any:
    try:
        signature = inspect.signature(
            generator
        )
        parameters = list(
            signature.parameters.values()
        )
    except Exception:
        parameters = []
    # =====================================================
    # ASYNC FUNCTION
    # =====================================================
    if inspect.iscoroutinefunction(
        generator
    ):
        if len(parameters) == 0:
            return await generator()
        if len(parameters) == 1:
            parameter_name = (
                parameters[0]
                .name
                .lower()
            )
            if "bot" in parameter_name:
                return await generator(
                    bot
                )
            if "market" in parameter_name:
                return await generator(
                    market
                )
            return await generator(
                bot
            )
        if len(parameters) == 2:
            return await generator(
                bot,
                market,
            )
        return await generator(
            bot,
            market,
            parameters,
        )
    # =====================================================
    # SYNC FUNCTION
    # =====================================================
    if len(parameters) == 0:
        return generator()
    if len(parameters) == 1:
        parameter_name = (
            parameters[0]
            .name
            .lower()
        )
        if "bot" in parameter_name:
            return generator(
                bot
            )
        if "market" in parameter_name:
            return generator(
                market
            )
        return generator(
            bot
        )
    if len(parameters) == 2:
        return generator(
            bot,
            market,
        )
    return generator(
        bot,
        market,
        parameters,
    )
# =========================================================
# OLD SIGNAL GENERATION LOOP
# =========================================================
async def signal_generation_loop(
    bot: Bot,
    market: MarketClient,
) -> None:
    logger.info(
        "Signal generation loop started."
    )
    generator = _load_generator(
        market
    )
    if generator is None:
        logger.warning(
            "No legacy signal generator found."
        )
        logger.warning(
            "This does NOT stop the automatic "
            "SignalScanner."
        )
    else:
        logger.info(
            "Legacy signal generation engine connected."
        )
    interval = _get_analysis_interval()
    logger.info(
        "Legacy signal analysis interval: %s seconds.",
        interval,
    )
    # =====================================================
    # MAIN LOOP
    # =====================================================
    while True:
        try:
            if generator is None:
                await asyncio.sleep(
                    interval
                )
                continue
            logger.info(
                "Starting legacy market signal analysis..."
            )
            result = await _call_generator(
                generator,
                bot,
                market,
            )
            if result is None:
                logger.info(
                    "Legacy signal generator finished: "
                    "no qualifying signal."
                )
            else:
                logger.info(
                    "Legacy signal generator result: %s",
                    result,
                )
        except asyncio.CancelledError:
            logger.info(
                "Legacy signal generation loop cancelled."
            )
            raise
        except Exception:
            logger.exception(
                "Legacy signal generation error."
            )
        interval = _get_analysis_interval()
        logger.info(
            "Next legacy signal analysis in %s seconds.",
            interval,
        )
        try:
            await asyncio.sleep(
                interval
            )
        except asyncio.CancelledError:
            logger.info(
                "Legacy signal generation sleep cancelled."
            )
            raise
# =========================================================
# AUTOMATIC SIGNAL SCANNER
# =========================================================
class AutomaticSignalScanner:
    """
    Обёртка над SignalScanner.
    Нужна для того, чтобы:
        SignalScanner
    автоматически отправлял найденные сигналы
    владельцу Telegram-бота.
    OWNER_ID берётся из config.py.
    """
    def __init__(
        self,
        bot: Bot,
        market: MarketClient,
    ) -> None:
        self.bot = bot
        self.market = market
        self.scanner = SignalScanner(
            market_client=market,
            send_signal=self.send_signal,
        )
    # =====================================================
    # SEND SIGNAL
    # =====================================================
    async def send_signal(
        self,
        signal: TradingSignal,
    ) -> None:
        text = (
            SignalScanner.format_signal(
                signal
            )
        )
        await self.bot.send_message(
            chat_id=OWNER_ID,
            text=text,
            parse_mode="HTML",
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
    # =====================================================
    # START
    # =====================================================
    async def start(
        self,
    ) -> None:
        logger.info(
            "Starting automatic signal scanner..."
        )
        await self.scanner.start()
        logger.info(
            (
                "Automatic signal scanner started | "
                "owner=%s"
            ),
            OWNER_ID,
        )
    # =====================================================
    # STOP
    # =====================================================
    async def stop(
        self,
    ) -> None:
        logger.info(
            "Stopping automatic signal scanner..."
        )
        await self.scanner.stop()
        logger.info(
            "Automatic signal scanner stopped."
        )
# =========================================================
# SCHEDULER
# =========================================================
class Scheduler:
    def __init__(
        self,
        bot: Bot,
        market: MarketClient,
    ) -> None:
        self.bot = bot
        self.market = market
        self.tasks: list[
            asyncio.Task
        ] = []
        # =================================================
        # AUTOMATIC SCANNER
        # =================================================
        self.automatic_scanner = (
            AutomaticSignalScanner(
                bot=bot,
                market=market,
            )
        )
        self._scanner_started = False
    # =====================================================
    # START
    # =====================================================
    async def start(
        self,
    ) -> None:
        # -------------------------------------------------
        # ЗАЩИТА ОТ ПОВТОРНОГО ЗАПУСКА
        # -------------------------------------------------
        active_tasks = [
            task
            for task in self.tasks
            if not task.done()
        ]
        if active_tasks:
            logger.warning(
                "Scheduler already started."
            )
            return
        self.tasks.clear()
        logger.info(
            "Starting scheduler..."
        )
        # =================================================
        # TASK 1
        # LEGACY SIGNAL GENERATION
        # =================================================
        generation_task = (
            asyncio.create_task(
                signal_generation_loop(
                    self.bot,
                    self.market,
                ),
                name="signal_generation",
            )
        )
        # =================================================
        # TASK 2
        # SIGNAL WARNING
        # =================================================
        warning_task = (
            asyncio.create_task(
                warning_scheduler(
                    self.bot
                ),
                name="signal_warning",
            )
        )
        # =================================================
        # TASK 3
        # RESULT CHECKER
        # =================================================
        result_task = (
            asyncio.create_task(
                result_checker_loop(
                    self.bot,
                    self.market,
                ),
                name="signal_result_checker",
            )
        )
        # =================================================
        # AUTOMATIC SCANNER
        # =================================================
        scanner_task = (
            asyncio.create_task(
                self.automatic_scanner.start(),
                name="automatic_signal_scanner",
            )
        )
        # =================================================
        # SAVE TASKS
        # =================================================
        self.tasks = [
            generation_task,
            warning_task,
            result_task,
            scanner_task,
        ]
        self._scanner_started = True
        logger.info(
            "Scheduler started: %s tasks.",
            len(self.tasks),
        )
        logger.info(
            "Scheduler tasks:"
        )
        for task in self.tasks:
            logger.info(
                " - %s",
                task.get_name(),
            )
        logger.info(
            "========================================"
        )
        logger.info(
            "AUTOMATIC SIGNAL SYSTEM ENABLED"
        )
        logger.info(
            "Signals will be scanned automatically."
        )
        logger.info(
            "Signals will be sent to OWNER_ID=%s",
            OWNER_ID,
        )
        logger.info(
            "========================================"
        )
    # =====================================================
    # STOP
    # =====================================================
    async def stop(
        self,
    ) -> None:
        if not self.tasks:
            # Даже если task list пуст,
            # на всякий случай останавливаем scanner.
            if self._scanner_started:
                try:
                    await self.automatic_scanner.stop()
                except Exception:
                    logger.exception(
                        "Automatic scanner shutdown error."
                    )
                self._scanner_started = False
            return
        logger.info(
            "Stopping scheduler..."
        )
        # =================================================
        # STOP AUTOMATIC SCANNER
        # =================================================
        if self._scanner_started:
            try:
                await self.automatic_scanner.stop()
            except Exception:
                logger.exception(
                    "Automatic scanner shutdown error."
                )
            self._scanner_started = False
        # =================================================
        # CANCEL TASKS
        # =================================================
        for task in self.tasks:
            if not task.done():
                task.cancel()
        # =================================================
        # WAIT
        # =================================================
        results = await asyncio.gather(
            *self.tasks,
            return_exceptions=True,
        )
        # =================================================
        # CHECK RESULTS
        # =================================================
        for task, result in zip(
            self.tasks,
            results,
        ):
            if isinstance(
                result,
                Exception,
            ):
                logger.debug(
                    (
                        "Scheduler task %s "
                        "stopped with: %s"
                    ),
                    task.get_name(),
                    result,
                )
        # =================================================
        # CLEAR
        # =================================================
        self.tasks.clear()
        logger.info(
            "Scheduler stopped."
        )
# =========================================================
# PUBLIC API
# =========================================================
__all__ = [
    "Scheduler",
    "signal_generation_loop",
    "AutomaticSignalScanner",
]
