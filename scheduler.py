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
# SIGNAL SCANNER
# =========================================================

SCANNER_MODULE = "signal_scanner"
SCANNER_CLASS = "SignalScanner"


# =========================================================
# LEGACY SIGNAL GENERATOR DISCOVERY
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
# GET ANALYSIS INTERVAL
# =========================================================


def _get_analysis_interval() -> int:
    """
    Получает интервал анализа из config.py.

    Используется:

        SIGNAL_ANALYSIS_INTERVAL

    Если настройки нет — 300 секунд.

    ВАЖНО:

    Текущий SignalScanner также имеет собственный
    SIGNAL_SCAN_INTERVAL.

    Для scanner режима scheduler НЕ использует
    этот интервал для запуска циклов.

    SignalScanner сам управляет своими циклами.
    """

    try:
        from config import SIGNAL_ANALYSIS_INTERVAL

        return max(
            1,
            int(SIGNAL_ANALYSIS_INTERVAL),
        )

    except Exception:
        logger.warning(
            (
                "SIGNAL_ANALYSIS_INTERVAL "
                "is unavailable. "
                "Using 300 seconds."
            )
        )

        return 300


# =========================================================
# CREATE SIGNAL SCANNER
# =========================================================


def _create_signal_scanner(
    market: MarketClient,
) -> Any | None:
    """
    Создаёт текущий SignalScanner.

    Ожидается:

        signal_scanner.py
            └── SignalScanner

    Конструктор текущего scanner:

        SignalScanner(
            market_client=market,
        )

    Дополнительно поддерживается старый вариант:

        SignalScanner(market)
    """

    try:
        module = importlib.import_module(
            SCANNER_MODULE
        )

    except ModuleNotFoundError:
        logger.warning(
            "signal_scanner.py not found."
        )
        return None

    except Exception:
        logger.exception(
            "Failed to import signal_scanner.py."
        )
        return None

    scanner_class = getattr(
        module,
        SCANNER_CLASS,
        None,
    )

    if scanner_class is None:
        logger.error(
            (
                "SignalScanner class was not "
                "found in signal_scanner.py."
            )
        )
        return None

    logger.info(
        "SignalScanner class found."
    )

    # =====================================================
    # CURRENT API
    # =====================================================

    try:
        scanner = scanner_class(
            market_client=market,
        )

        logger.info(
            (
                "SignalScanner initialized "
                "using market_client=market."
            )
        )

        return scanner

    except TypeError:
        pass

    except Exception:
        logger.exception(
            "Failed to initialize SignalScanner."
        )
        return None

    # =====================================================
    # LEGACY API
    # =====================================================

    try:
        scanner = scanner_class(
            market
        )

        logger.info(
            (
                "SignalScanner initialized "
                "using positional market argument."
            )
        )

        return scanner

    except Exception:
        logger.exception(
            "Failed to initialize SignalScanner."
        )

        return None


# =========================================================
# CALL GENERATOR
# =========================================================


async def _call_generator(
    generator: Any,
    bot: Bot,
    market: MarketClient,
) -> Any:
    """
    Универсальный запуск старого генератора.

    Поддерживает:

        generate()
        generate(bot)
        generate(market)
        generate(bot, market)

    Также поддерживает sync-функции.
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
    # ARGUMENT BUILDER
    # =====================================================

    def build_arguments() -> list[Any]:
        if len(parameters) == 0:
            return []

        if len(parameters) == 1:
            parameter_name = (
                parameters[0]
                .name
                .lower()
            )

            if "market" in parameter_name:
                return [market]

            if "bot" in parameter_name:
                return [bot]

            return [bot]

        if len(parameters) == 2:
            return [
                bot,
                market,
            ]

        return [
            bot,
            market,
        ]

    arguments = build_arguments()

    # =====================================================
    # ASYNC
    # =====================================================

    if inspect.iscoroutinefunction(
        generator
    ):
        return await generator(
            *arguments
        )

    # =====================================================
    # SYNC
    # =====================================================

    result = generator(
        *arguments
    )

    if inspect.isawaitable(result):
        return await result

    return result


# =========================================================
# RUN SIGNAL SCANNER
# =========================================================


async def _run_signal_scanner(
    scanner: Any,
) -> None:
    """
    Запускает текущий SignalScanner.

    Текущий scanner.py содержит:

        _running
        _stop_event
        scan_once()

    Поэтому scheduler вручную активирует scanner
    и вызывает scan_once() циклически.

    Это сделано намеренно, потому что в текущем
    SignalScanner scan_once() прекращает работу,
    если:

        self._running == False
    """

    logger.info(
        "================================================"
    )

    logger.info(
        "SIGNAL SCANNER MODE"
    )

    logger.info(
        "================================================"
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
    # ACTIVATE
    # =====================================================

    try:
        scanner._running = True

    except Exception:
        logger.exception(
            "Failed to activate SignalScanner."
        )
        return

    stop_event = getattr(
        scanner,
        "_stop_event",
        None,
    )

    if stop_event is not None:
        try:
            stop_event.clear()

        except Exception:
            logger.debug(
                "Could not clear scanner stop event.",
                exc_info=True,
            )

    # =====================================================
    # SCANNER CONFIG
    # =====================================================

    scan_interval = getattr(
        scanner,
        "scan_interval",
        None,
    )

    candle_limit = getattr(
        scanner,
        "candle_limit",
        None,
    )

    minimum_quality = getattr(
        scanner,
        "minimum_quality",
        None,
    )

    logger.info(
        (
            "SignalScanner active | "
            "pairs=%s | "
            "timeframes=%s | "
            "interval=%ss | "
            "candles=%s | "
            "minimum_quality=%.1f"
        ),
        len(symbols),
        timeframes,
        scan_interval,
        candle_limit,
        float(
            minimum_quality
            if minimum_quality is not None
            else 0.0
        ),
    )

    # =====================================================
    # MAIN LOOP
    # =====================================================

    try:
        while True:

            # -------------------------------------------------
            # STOP CHECK
            # -------------------------------------------------

            if not getattr(
                scanner,
                "_running",
                True,
            ):
                logger.info(
                    "SignalScanner requested stop."
                )
                break

            # -------------------------------------------------
            # SCAN
            # -------------------------------------------------

            try:
                logger.info(
                    "Starting SignalScanner analysis..."
                )

                signals = await scanner.scan_once()

                # =================================================
                # NO SIGNAL
                # =================================================

                if not signals:
                    logger.info(
                        (
                            "⛔ Сейчас сигнала нет. "
                            "Проверенные пары не прошли "
                            "Quality Filter."
                        )
                    )

                # =================================================
                # SIGNALS FOUND
                # =================================================

                else:
                    logger.info(
                        (
                            "🚨 SignalScanner produced "
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

            # =================================================
            # INTERVAL
            # =================================================

            interval = getattr(
                scanner,
                "scan_interval",
                None,
            )

            try:
                interval = max(
                    1,
                    int(interval),
                )

            except Exception:
                interval = 300

            logger.info(
                (
                    "Next SignalScanner analysis "
                    "in %s seconds."
                ),
                interval,
            )

            # =================================================
            # WAIT
            # =================================================

            try:

                if stop_event is not None:

                    try:
                        await asyncio.wait_for(
                            stop_event.wait(),
                            timeout=interval,
                        )

                        logger.info(
                            "SignalScanner stop event received."
                        )

                        break

                    except asyncio.TimeoutError:
                        pass

                else:
                    await asyncio.sleep(
                        interval
                    )

            except asyncio.CancelledError:
                raise

    finally:

        # =====================================================
        # DEACTIVATE
        # =====================================================

        try:
            scanner._running = False

        except Exception:
            pass

        logger.info(
            "SignalScanner loop stopped."
        )


# =========================================================
# LEGACY GENERATOR DISCOVERY
# =========================================================


def _load_legacy_generator(
    market: MarketClient,
) -> Any | None:
    """
    Старый fallback.

    Используется только если SignalScanner
    отсутствует или не может быть создан.

    Ищет:

        signal_generator.py
        signal_engine.py
        signal_analyzer.py
        analyzer.py
        ...

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
                (
                    "Failed to import "
                    "legacy signal module: %s"
                ),
                module_name,
            )
            continue

        # =================================================
        # FUNCTIONS
        # =================================================

        for function_name in GENERATOR_FUNCTIONS:

            function = getattr(
                module,
                function_name,
                None,
            )

            if not callable(function):
                continue

            logger.info(
                (
                    "Legacy signal generator found: "
                    "%s.%s"
                ),
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

        instance = None

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
                    (
                        "Failed to initialize "
                        "SignalGenerator from %s"
                    ),
                    module_name,
                )

        except Exception:
            logger.exception(
                (
                    "Failed to initialize "
                    "SignalGenerator from %s"
                ),
                module_name,
            )

        if instance is None:
            continue

        # =================================================
        # generate()
        # =================================================

        generate = getattr(
            instance,
            "generate",
            None,
        )

        if callable(generate):

            logger.info(
                (
                    "Legacy SignalGenerator connected: "
                    "%s.SignalGenerator.generate"
                ),
                module_name,
            )

            return generate

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
                (
                    "Legacy signal method found: "
                    "%s.SignalGenerator.%s"
                ),
                module_name,
                method_name,
            )

            return method

    return None


# =========================================================
# LEGACY SIGNAL GENERATION LOOP
# =========================================================


async def _run_legacy_generator(
    generator: Any,
    bot: Bot,
    market: MarketClient,
) -> None:
    """
    Старый режим генерации сигналов.

    Нужен только для совместимости.
    """

    logger.info(
        "Legacy signal generator mode started."
    )

    interval = _get_analysis_interval()

    while True:

        try:

            logger.info(
                "Starting legacy market signal analysis..."
            )

            result = await _call_generator(
                generator,
                bot,
                market,
            )

            # =================================================
            # RESULT
            # =================================================

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

                if not result:

                    logger.info(
                        (
                            "⛔ Сейчас сигнала нет. "
                            "Список сигналов пуст."
                        )
                    )

                else:

                    logger.info(
                        (
                            "Legacy signal generator "
                            "returned %s signal(s)."
                        ),
                        len(result),
                    )

            else:

                logger.info(
                    "Legacy generator result: %s",
                    result,
                )

        except asyncio.CancelledError:

            logger.info(
                "Legacy signal generation cancelled."
            )

            raise

        except Exception:

            logger.exception(
                "Legacy signal generation error."
            )

        # =================================================
        # INTERVAL
        # =================================================

        interval = _get_analysis_interval()

        logger.info(
            (
                "Next legacy signal analysis "
                "in %s seconds."
            ),
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
# SIGNAL GENERATION LOOP
# =========================================================


async def signal_generation_loop(
    bot: Bot,
    market: MarketClient,
) -> None:
    """
    Главный цикл генерации сигналов.

    Приоритет:

        1. Текущий SignalScanner
        2. Старый SignalGenerator

    То есть текущий signal_scanner.py является
    основным источником сигналов.
    """

    logger.info(
        "================================================"
    )

    logger.info(
        "SIGNAL GENERATION LOOP STARTED"
    )

    logger.info(
        "================================================"
    )

    # =====================================================
    # CURRENT SIGNAL SCANNER
    # =====================================================

    scanner = _create_signal_scanner(
        market
    )

    if scanner is not None:

        scan_once = getattr(
            scanner,
            "scan_once",
            None,
        )

        if callable(scan_once):

            logger.info(
                "Current SignalScanner selected."
            )

            await _run_signal_scanner(
                scanner
            )

            return

        logger.warning(
            (
                "SignalScanner exists but "
                "scan_once() is unavailable."
            )
        )

    # =====================================================
    # LEGACY FALLBACK
    # =====================================================

    logger.warning(
        (
            "Current SignalScanner unavailable. "
            "Trying legacy signal generator."
        )
    )

    generator = _load_legacy_generator(
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
            "Scheduler cannot create signals."
        )

        logger.error(
            "Expected:"
        )

        logger.error(
            " - signal_scanner.py"
        )

        logger.error(
            " - SignalScanner"
        )

        logger.error(
            "================================================"
        )

        return

    await _run_legacy_generator(
        generator,
        bot,
        market,
    )


# =========================================================
# SCHEDULER
# =========================================================


class Scheduler:
    """
    Главный scheduler проекта.

    Запускает:

        1. SignalScanner
        2. Signal Warning Scheduler
        3. Result Checker

    """

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

        self._started = False

    # =====================================================
    # START
    # =====================================================

    async def start(
        self,
    ) -> None:

        # =================================================
        # DOUBLE START PROTECTION
        # =================================================

        active_tasks = [
            task
            for task in self.tasks
            if not task.done()
        ]

        if active_tasks:

            logger.warning(
                "Scheduler already started."
            )

            self._started = True

            return

        # =================================================
        # RESET
        # =================================================

        self.tasks.clear()

        self._started = True

        logger.info(
            "================================================"
        )

        logger.info(
            "STARTING TEYZUS SCHEDULER"
        )

        logger.info(
            "================================================"
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
        # WARNING SCHEDULER
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
        # SAVE
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

            self._started = False

            return

        logger.info(
            "================================================"
        )

        logger.info(
            "STOPPING TEYZUS SCHEDULER"
        )

        logger.info(
            "================================================"
        )

        # =================================================
        # CANCEL
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
        # LOG
        # =================================================

        for task, result in zip(
            self.tasks,
            results,
        ):

            if isinstance(
                result,
                BaseException,
            ):

                if isinstance(
                    result,
                    asyncio.CancelledError,
                ):
                    continue

                logger.error(
                    (
                        "Scheduler task %s "
                        "stopped with error: %s"
                    ),
                    task.get_name(),
                    result,
                )

        # =================================================
        # CLEAR
        # =================================================

        self.tasks.clear()

        self._started = False

        logger.info(
            "Scheduler stopped."
        )

    # =====================================================
    # RUNNING
    # =====================================================

    @property
    def running(self) -> bool:
        return any(
            not task.done()
            for task in self.tasks
        )


# =========================================================
# PUBLIC API
# =========================================================


__all__ = [
    "Scheduler",
    "signal_generation_loop",
]
