from __future__ import annotations
import asyncio
import importlib
import inspect
import logging
from typing import Any
from aiogram import Bot
from market import MarketClient
from result_checker import result_checker_loop
from signal_warning.scheduler import warning_scheduler
logger = logging.getLogger("scheduler")
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
# SIGNAL SCANNER DISCOVERY
# =========================================================
SCANNER_MODULE = "signal_scanner"
SCANNER_CLASS = "SignalScanner"
# =========================================================
# LOAD SIGNAL GENERATOR
# =========================================================
def _load_generator(
    market: MarketClient,
) -> Any | None:
    """
    Ищет существующий генератор сигналов.
    Порядок:
    1. signal_generator.py
    2. другие совместимые генераторы
    3. SignalGenerator
    4. SignalScanner
    ВАЖНО:
    SignalEngine сам по себе НЕ считается генератором,
    потому что его analyze() требует candles.
    SignalScanner используется как полноценный fallback.
    """
    # =====================================================
    # EXISTING GENERATOR MODULES
    # =====================================================
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
        # ORDINARY FUNCTIONS
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
        # SIGNAL GENERATOR CLASS
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
        instance: Any | None = None
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
        except Exception:
            logger.exception(
                "Failed to initialize "
                "SignalGenerator from %s",
                module_name,
            )
        if instance is None:
            continue
        # =================================================
        # generate()
        # =================================================
        generate_method = getattr(
            instance,
            "generate",
            None,
        )
        if callable(generate_method):
            logger.info(
                "SignalGenerator connected: "
                "%s.SignalGenerator.generate",
                module_name,
            )
            return generate_method
        # =================================================
        # OTHER METHODS
        # =================================================
        for method_name in GENERATOR_FUNCTIONS:
            method = getattr(
                instance,
                method_name,
                None,
            )
            if not callable(method):
                continue
            logger.info(
                "Signal generator method found: "
                "%s.SignalGenerator.%s",
                module_name,
                method_name,
            )
            return method
    # =====================================================
    # SIGNAL SCANNER FALLBACK
    # =====================================================
    try:
        scanner_module = importlib.import_module(
            SCANNER_MODULE
        )
    except ModuleNotFoundError:
        logger.warning(
            "signal_scanner.py not found."
        )
        return None
    except Exception:
        logger.exception(
            "Failed to import signal_scanner."
        )
        return None
    scanner_class = getattr(
        scanner_module,
        SCANNER_CLASS,
        None,
    )
    if scanner_class is None:
        logger.warning(
            "SignalScanner class not found."
        )
        return None
    logger.info(
        "SignalScanner class found."
    )
    try:
        scanner = scanner_class(
            market_client=market,
        )
    except TypeError:
        try:
            scanner = scanner_class(
                market
            )
        except Exception:
            logger.exception(
                "Failed to initialize SignalScanner."
            )
            return None
    except Exception:
        logger.exception(
            "Failed to initialize SignalScanner."
        )
        return None
    scan_once = getattr(
        scanner,
        "scan_once",
        None,
    )
    if not callable(scan_once):
        logger.error(
            "SignalScanner does not provide scan_once()."
        )
        return None
    # -----------------------------------------------------
    # Помечаем scanner специальным атрибутом.
    #
    # Это позволяет signal_generation_loop понять,
    # что перед ним именно SignalScanner.
    # -----------------------------------------------------
    try:
        setattr(
            scan_once,
            "__teyzus_signal_scanner__",
            scanner,
        )
    except Exception:
        pass
    logger.info(
        "SignalScanner connected: "
        "SignalScanner.scan_once"
    )
    return scan_once
# =========================================================
# GET ANALYSIS INTERVAL
# =========================================================
def _get_analysis_interval() -> int:
    """
    Использует существующую настройку:
        SIGNAL_ANALYSIS_INTERVAL
    из config.py.
    Никакого SIGNAL_SCAN_INTERVAL здесь нет.
    Это устраняет ошибку:
        ImportError:
        cannot import name 'SIGNAL_SCAN_INTERVAL'
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
            (
                "SIGNAL_ANALYSIS_INTERVAL "
                "is unavailable. "
                "Using 20 seconds."
            )
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
    Также поддерживает обычные sync-функции.
    """
    # =====================================================
    # SIGNATURE
    # =====================================================
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
    # ONLY POSITIONAL PARAMETERS
    # =====================================================
    positional_parameters = [
        parameter
        for parameter in parameters
        if parameter.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
    ]
    parameters = positional_parameters
    # =====================================================
    # ASYNC GENERATOR
    # =====================================================
    if inspect.iscoroutinefunction(
        generator
    ):
        # -------------------------------------------------
        # 0 arguments
        # -------------------------------------------------
        if len(parameters) == 0:
            return await generator()
        # -------------------------------------------------
        # 1 argument
        # -------------------------------------------------
        if len(parameters) == 1:
            parameter_name = (
                parameters[0]
                .name
                .lower()
            )
            if "market" in parameter_name:
                return await generator(
                    market
                )
            if "bot" in parameter_name:
                return await generator(
                    bot
                )
            return await generator(
                bot
            )
        # -------------------------------------------------
        # 2 arguments
        # -------------------------------------------------
        if len(parameters) == 2:
            return await generator(
                bot,
                market,
            )
        # -------------------------------------------------
        # More than 2
        # -------------------------------------------------
        return await generator(
            bot,
            market,
            parameters,
        )
    # =====================================================
    # SYNC GENERATOR
    # =====================================================
    if len(parameters) == 0:
        result = generator()
        if inspect.isawaitable(result):
            return await result
        return result
    if len(parameters) == 1:
        parameter_name = (
            parameters[0]
            .name
            .lower()
        )
        if "market" in parameter_name:
            result = generator(
                market
            )
        elif "bot" in parameter_name:
            result = generator(
                bot
            )
        else:
            result = generator(
                bot
            )
        if inspect.isawaitable(result):
            return await result
        return result
    if len(parameters) == 2:
        result = generator(
            bot,
            market,
        )
        if inspect.isawaitable(result):
            return await result
        return result
    result = generator(
        bot,
        market,
        parameters,
    )
    if inspect.isawaitable(result):
        return await result
    return result
# =========================================================
# SIGNAL SCANNER LOOP
# =========================================================
async def _run_signal_scanner(
    scanner: Any,
) -> None:
    """
    Запускает SignalScanner напрямую.
    Критически важно:
    SignalScanner.scan_once() проверяет:
        if not self._running:
            break
    Поэтому нельзя просто вызвать scan_once()
    на новом экземпляре.
    Здесь scanner переводится в running-состояние
    и после этого scan_once() вызывается циклически.
    """
    logger.info(
        "SignalScanner loop started."
    )
    # =====================================================
    # VALIDATION
    # =====================================================
    symbols = getattr(
        scanner,
        "symbols",
        None,
    )
    timeframes = getattr(
        scanner,
        "timeframes",
        None,
    )
    if not symbols:
        logger.error(
            "SignalScanner has no symbols."
        )
        return
    if not timeframes:
        logger.error(
            "SignalScanner has no timeframes."
        )
        return
    # =====================================================
    # ACTIVATE SCANNER
    # =====================================================
    try:
        scanner._running = True
        stop_event = getattr(
            scanner,
            "_stop_event",
            None,
        )
        if stop_event is not None:
            try:
                stop_event.clear()
            except Exception:
                pass
    except Exception:
        logger.exception(
            "Failed to activate SignalScanner."
        )
        return
    # =====================================================
    # INTERVAL
    # =====================================================
    interval = _get_analysis_interval()
    logger.info(
        (
            "SignalScanner active | "
            "pairs=%s | "
            "timeframes=%s | "
            "interval=%ss"
        ),
        len(symbols),
        timeframes,
        interval,
    )
    # =====================================================
    # MAIN LOOP
    # =====================================================
    try:
        while True:
            try:
                logger.info(
                    "Starting SignalScanner analysis..."
                )
                signals = await scanner.scan_once()
                # -------------------------------------------------
                # RESULT
                # -------------------------------------------------
                if not signals:
                    logger.info(
                        (
                            "⛔ Сейчас сигнала нет. "
                            "Все проверенные варианты "
                            "не прошли фильтрацию."
                        )
                    )
                else:
                    logger.info(
                        (
                            "SignalScanner produced "
                            "%s qualifying signal(s)."
                        ),
                        len(signals),
                    )
                    for signal in signals:
                        logger.info(
                            (
                                "QUALIFIED SIGNAL | "
                                "symbol=%s | "
                                "direction=%s | "
                                "quality=%.2f | "
                                "confirmations=%s/%s"
                            ),
                            getattr(
                                signal,
                                "symbol",
                                "?",
                            ),
                            getattr(
                                signal,
                                "direction",
                                "?",
                            ),
                            float(
                                getattr(
                                    signal,
                                    "quality_score",
                                    0.0,
                                )
                            ),
                            getattr(
                                signal,
                                "confirmations",
                                0,
                            ),
                            getattr(
                                signal,
                                "total_checks",
                                0,
                            ),
                        )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "SignalScanner analysis error."
                )
            # -----------------------------------------------------
            # RELOAD INTERVAL
            # -----------------------------------------------------
            interval = _get_analysis_interval()
            logger.info(
                "Next SignalScanner analysis in %s seconds.",
                interval,
            )
            try:
                await asyncio.sleep(
                    interval
                )
            except asyncio.CancelledError:
                raise
    finally:
        # =========================================================
        # DEACTIVATE
        # =========================================================
        try:
            scanner._running = False
        except Exception:
            pass
        logger.info(
            "SignalScanner loop stopped."
        )
# =========================================================
# SIGNAL GENERATION LOOP
# =========================================================
async def signal_generation_loop(
    bot: Bot,
    market: MarketClient,
) -> None:
    """
    Главный цикл генерации сигналов.
    Если найден SignalScanner, он запускается
    через отдельный scanner-loop.
    Если найден старый generator,
    используется совместимый режим.
    """
    logger.info(
        "Signal generation loop started."
    )
    # =====================================================
    # LOAD GENERATOR
    # =====================================================
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
            "Expected module:"
        )
        logger.error(
            " - signal_scanner.py"
        )
        logger.error(
            "Expected classes:"
        )
        logger.error(
            " - SignalGenerator"
        )
        logger.error(
            " - SignalScanner"
        )
        logger.error(
            "================================================"
        )
        return
    # =====================================================
    # CHECK FOR SIGNAL SCANNER
    # =====================================================
    scanner = getattr(
        generator,
        "__teyzus_signal_scanner__",
        None,
    )
    if scanner is not None:
        logger.info(
            "SignalScanner mode selected."
        )
        await _run_signal_scanner(
            scanner
        )
        return
    # =====================================================
    # NORMAL GENERATOR MODE
    # =====================================================
    logger.info(
        "Signal generation engine connected."
    )
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
            result = await _call_generator(
                generator,
                bot,
                market,
            )
            if result is None:
                logger.info(
                    (
                        "⛔ Сейчас сигнала нет. "
                        "Генератор не вернул "
                        "подходящий сигнал."
                    )
                )
            elif isinstance(
                result,
                (list, tuple),
            ):
                if len(result) == 0:
                    logger.info(
                        (
                            "⛔ Сейчас сигнала нет. "
                            "Список сигналов пуст."
                        )
                    )
                else:
                    logger.info(
                        "Signal generator returned %s signal(s).",
                        len(result),
                    )
            else:
                logger.info(
                    "Signal generator result: %s",
                    result,
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
    ) -> None:
        self.bot = bot
        self.market = market
        self.tasks: list[
            asyncio.Task[Any]
        ] = []
    # =====================================================
    # START
    # =====================================================
    async def start(
        self,
    ) -> None:
        # -------------------------------------------------
        # PROTECTION FROM DOUBLE START
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
        # CLEAR OLD TASKS
        # -------------------------------------------------
        self.tasks.clear()
        logger.info(
            "Starting scheduler..."
        )
        # =================================================
        # TASK 1
        # SIGNAL GENERATION
        # =================================================
        generation_task = asyncio.create_task(
            signal_generation_loop(
                self.bot,
                self.market,
            ),
            name="signal_generation",
        )
        # =================================================
        # TASK 2
        # SIGNAL WARNING
        # =================================================
        warning_task = asyncio.create_task(
            warning_scheduler(
                self.bot
            ),
            name="signal_warning",
        )
        # =================================================
        # TASK 3
        # RESULT CHECKER
        # =================================================
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
        # CANCEL TASKS
        # -------------------------------------------------
        for task in self.tasks:
            if not task.done():
                task.cancel()
        # -------------------------------------------------
        # WAIT
        # -------------------------------------------------
        results = await asyncio.gather(
            *self.tasks,
            return_exceptions=True,
        )
        # -------------------------------------------------
        # LOG ERRORS
        # -------------------------------------------------
        for task, result in zip(
            self.tasks,
            results,
        ):
            if isinstance(
                result,
                Exception,
            ):
                if isinstance(
                    result,
                    asyncio.CancelledError,
                ):
                    continue
                logger.debug(
                    (
                        "Scheduler task %s "
                        "stopped with: %s"
                    ),
                    task.get_name(),
                    result,
                )
        # -------------------------------------------------
        # CLEAR
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
