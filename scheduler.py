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
def _load_generator() -> Any | None:
    """
    Пытается найти существующий генератор сигналов
    в проекте.
    Мы специально не создаём новую логику анализа здесь.
    Scheduler должен запускать уже существующий движок.
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
                "Signal generator found: %s.%s",
                module_name,
                function_name,
            )
            return function
    return None
async def _call_generator(
    generator: Any,
    bot: Bot,
    market: MarketClient,
) -> Any:
    """
    Запускает найденный генератор.
    Поддерживает несколько вариантов сигнатуры,
    чтобы не ломать существующий код.
    """
    try:
        signature = inspect.signature(
            generator
        )
        parameters = list(
            signature.parameters.values()
        )
    except Exception:
        parameters = []
    # -----------------------------------------------------
    # Если функция async
    # -----------------------------------------------------
    if inspect.iscoroutinefunction(
        generator
    ):
        # 0 аргументов
        if len(parameters) == 0:
            return await generator()
        # 1 аргумент
        if len(parameters) == 1:
            name = (
                parameters[0]
                .name
                .lower()
            )
            if "bot" in name:
                return await generator(
                    bot
                )
            return await generator(
                market
            )
        # 2 аргумента
        if len(parameters) == 2:
            return await generator(
                bot,
                market,
            )
        # 3+ аргумента
        return await generator(
            bot,
            market,
            parameters,
        )
    # -----------------------------------------------------
    # Синхронная функция
    # -----------------------------------------------------
    if len(parameters) == 0:
        return generator()
    if len(parameters) == 1:
        name = (
            parameters[0]
            .name
            .lower()
        )
        if "bot" in name:
            return generator(
                bot
            )
        return generator(
            market
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
# SIGNAL GENERATION LOOP
# =========================================================
async def signal_generation_loop(
    bot: Bot,
    market: MarketClient,
) -> None:
    logger.info(
        "Signal generation loop started."
    )
    generator = _load_generator()
    if generator is None:
        logger.error(
            "================================================"
        )
        logger.error(
            "NO SIGNAL GENERATOR FOUND."
        )
        logger.error(
            "Scheduler cannot create new signals."
        )
        logger.error(
            "Expected one of modules: %s",
            ", ".join(GENERATOR_MODULES),
        )
        logger.error(
            "Expected one of functions: %s",
            ", ".join(GENERATOR_FUNCTIONS),
        )
        logger.error(
            "================================================"
        )
        return
    logger.info(
        "Signal generation engine connected."
    )
    while True:
        try:
            logger.info(
                "Starting market signal analysis..."
            )
            result = await _call_generator(
                generator,
                bot,
                market,
            )
            if result is not None:
                logger.info(
                    "Signal generator result: %s",
                    result,
                )
            else:
                logger.info(
                    "Signal generator finished: "
                    "no qualifying signal."
                )
        except asyncio.CancelledError:
            logger.info(
                "Signal generation loop cancelled."
            )
            raise
        except Exception:
            logger.exception(
                "Signal generation error."
            )
        # -------------------------------------------------
        # Следующая проверка через 20 секунд.
        #
        # Если SIGNAL_ANALYSIS_INTERVAL есть в config.py,
        # используем его.
        # -------------------------------------------------
        try:
            from config import (
                SIGNAL_ANALYSIS_INTERVAL,
            )
            interval = max(
                1,
                int(
                    SIGNAL_ANALYSIS_INTERVAL
                ),
            )
        except Exception:
            interval = 20
        await asyncio.sleep(
            interval
        )
# =========================================================
# SCHEDULER
# =========================================================
class Scheduler:
    def __init__(
        self,
        bot: Bot,
        market: MarketClient,
    ):
        self.bot = bot
        self.market = market
        self.tasks: list[
            asyncio.Task
        ] = []
    # =====================================================
    # START
    # =====================================================
    async def start(self) -> None:
        if self.tasks:
            logger.warning(
                "Scheduler already started."
            )
            return
        logger.info(
            "Starting scheduler..."
        )
        # -------------------------------------------------
        # TASK 1
        # Генерация новых сигналов
        # -------------------------------------------------
        generation_task = (
            asyncio.create_task(
                signal_generation_loop(
                    self.bot,
                    self.market,
                ),
                name="signal_generation",
            )
        )
        # -------------------------------------------------
        # TASK 2
        # Предупреждения
        # -------------------------------------------------
        warning_task = (
            asyncio.create_task(
                warning_scheduler(
                    self.bot
                ),
                name="signal_warning",
            )
        )
        # -------------------------------------------------
        # TASK 3
        # Проверка результатов
        # -------------------------------------------------
        result_task = (
            asyncio.create_task(
                result_checker_loop(
                    self.bot,
                    self.market,
                ),
                name="signal_result_checker",
            )
        )
        self.tasks = [
            generation_task,
            warning_task,
            result_task,
        ]
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
    # =====================================================
    # STOP
    # =====================================================
    async def stop(self) -> None:
        if not self.tasks:
            return
        logger.info(
            "Stopping scheduler..."
        )
        for task in self.tasks:
            if not task.done():
                task.cancel()
        results = await asyncio.gather(
            *self.tasks,
            return_exceptions=True,
        )
        for task, result in zip(
            self.tasks,
            results,
        ):
            if isinstance(
                result,
                Exception,
            ):
                logger.debug(
                    "Scheduler task %s "
                    "stopped with: %s",
                    task.get_name(),
                    result,
                )
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
]
