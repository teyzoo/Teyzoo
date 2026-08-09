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
    Текущий signal_generator.py TEYZUS
    использует именно второй вариант.
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
        # Обычная функция
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
        # SignalGenerator
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
        # Создаём экземпляр
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
        # Ищем generate
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
        # Дополнительные варианты методов
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
    Получает задержку между анализами.
    Основная переменная:
        SIGNAL_ANALYSIS_INTERVAL
    Если её нет или значение неправильное,
    используется 20 секунд.
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
    """
    Универсальный запуск генератора.
    Поддерживает:
        generate()
        generate(bot)
        generate(market)
        generate(bot, market)
    Для текущего:
        SignalGenerator.generate(bot)
    будет передан bot.
    """
    # -----------------------------------------------------
    # Получаем сигнатуру
    # -----------------------------------------------------
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
        # -------------------------------------------------
        # 0 аргументов
        # -------------------------------------------------
        if len(parameters) == 0:
            return await generator()
        # -------------------------------------------------
        # 1 аргумент
        # -------------------------------------------------
        if len(parameters) == 1:
            parameter_name = (
                parameters[0]
                .name
                .lower()
            )
            # generate(bot)
            if (
                "bot"
                in parameter_name
            ):
                return await generator(
                    bot
                )
            # generate(market)
            if (
                "market"
                in parameter_name
            ):
                return await generator(
                    market
                )
            # Для текущего TEYZUS
            # безопаснее всего передать bot.
            return await generator(
                bot
            )
        # -------------------------------------------------
        # 2 аргумента
        # -------------------------------------------------
        if len(parameters) == 2:
            return await generator(
                bot,
                market,
            )
        # -------------------------------------------------
        # Больше 2 аргументов
        # -------------------------------------------------
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
        if (
            "bot"
            in parameter_name
        ):
            return generator(
                bot
            )
        if (
            "market"
            in parameter_name
        ):
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
# SIGNAL GENERATION LOOP
# =========================================================
async def signal_generation_loop(
    bot: Bot,
    market: MarketClient,
) -> None:
    logger.info(
        "Signal generation loop started."
    )
    # -----------------------------------------------------
    # Ищем генератор
    # -----------------------------------------------------
    generator = _load_generator(
        market
    )
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
            "Expected modules:"
        )
        for module_name in GENERATOR_MODULES:
            logger.error(
                " - %s",
                module_name,
            )
        logger.error(
            "Expected functions:"
        )
        for function_name in GENERATOR_FUNCTIONS:
            logger.error(
                " - %s",
                function_name,
            )
        logger.error(
            "Expected class:"
        )
        logger.error(
            " - SignalGenerator"
        )
        logger.error(
            "Expected method:"
        )
        logger.error(
            " - SignalGenerator.generate"
        )
        logger.error(
            "================================================"
        )
        return
    # -----------------------------------------------------
    # Генератор найден
    # -----------------------------------------------------
    logger.info(
        "Signal generation engine connected."
    )
    # -----------------------------------------------------
    # Получаем задержку
    # -----------------------------------------------------
    interval = _get_analysis_interval()
    logger.info(
        "Signal analysis interval: %s seconds.",
        interval,
    )
    # =====================================================
    # MAIN LOOP
    # =====================================================
    while True:
        try:
            logger.info(
                "Starting market signal analysis..."
            )
            # ---------------------------------------------
            # Запускаем существующий генератор
            # ---------------------------------------------
            result = await _call_generator(
                generator,
                bot,
                market,
            )
            # ---------------------------------------------
            # Результат
            # ---------------------------------------------
            if result is None:
                logger.info(
                    "Signal generator finished: "
                    "no qualifying signal."
                )
            else:
                logger.info(
                    "Signal generator result: %s",
                    result,
                )
        # =================================================
        # CANCEL
        # =================================================
        except asyncio.CancelledError:
            logger.info(
                "Signal generation loop cancelled."
            )
            raise
        # =================================================
        # ERROR
        # =================================================
        except Exception:
            logger.exception(
                "Signal generation error."
            )
        # =================================================
        # DELAY
        # =================================================
        interval = _get_analysis_interval()
        logger.info(
            "Next signal analysis in %s seconds.",
            interval,
        )
        try:
            await asyncio.sleep(
                interval
            )
        except asyncio.CancelledError:
            logger.info(
                "Signal generation sleep cancelled."
            )
            raise
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
    async def start(
        self,
    ) -> None:
        # -------------------------------------------------
        # Защита от повторного запуска
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
        # -------------------------------------------------
        # Если старые задачи завершились,
        # очищаем список
        # -------------------------------------------------
        self.tasks.clear()
        logger.info(
            "Starting scheduler..."
        )
        # =================================================
        # TASK 1
        # SIGNAL GENERATION
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
        # SAVE TASKS
        # =================================================
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
    async def stop(
        self,
    ) -> None:
        if not self.tasks:
            return
        logger.info(
            "Stopping scheduler..."
        )
        # -------------------------------------------------
        # Cancel tasks
        # -------------------------------------------------
        for task in self.tasks:
            if not task.done():
                task.cancel()
        # -------------------------------------------------
        # Wait for tasks
        # -------------------------------------------------
        results = await asyncio.gather(
            *self.tasks,
            return_exceptions=True,
        )
        # -------------------------------------------------
        # Check results
        # -------------------------------------------------
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
        # -------------------------------------------------
        # Clear
        # -------------------------------------------------
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
