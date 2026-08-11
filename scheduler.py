from __future__ import annotations
import asyncio
import logging
import os
from typing import Any
logger = logging.getLogger("scheduler")
# =========================================================
# CONFIGURATION
# =========================================================
WARNING_INTERVAL = max(
    5,
    int(
        os.getenv(
            "SIGNAL_WARNING_INTERVAL",
            "15",
        )
    ),
)
RESULT_CHECK_INTERVAL = max(
    5,
    int(
        os.getenv(
            "SIGNAL_RESULT_CHECK_INTERVAL",
            "15",
        )
    ),
)
# =========================================================
# GLOBAL STATE
# =========================================================
_scheduler_running = False
_signal_scanner: Any | None = None
_scheduler_tasks: list[
    asyncio.Task[Any]
] = []
_shutdown_event = asyncio.Event()
_start_lock = asyncio.Lock()
_stop_lock = asyncio.Lock()
# =========================================================
# OPTIONAL EXTERNAL COMPONENTS
# =========================================================
_warning_scheduler: Any | None = None
_result_checker: Any | None = None
# =========================================================
# SAFE IMPORT HELPERS
# =========================================================
def _import_signal_scanner():
    """
    Импорт текущего SignalScanner.
    Используется локальный импорт, чтобы scheduler
    не создавал циклические импорты при запуске main.py.
    """
    from signal_scanner import SignalScanner
    return SignalScanner
def _import_warning_components():
    """
    Пытаемся найти существующий модуль предупреждений.
    Поддерживаются варианты:
        signal_warning.py
        warning_scheduler.py
    """
    candidates = (
        "signal_warning",
        "warning_scheduler",
    )
    for module_name in candidates:
        try:
            module = __import__(
                module_name
            )
            return module
        except ImportError:
            continue
        except Exception:
            logger.exception(
                "Failed importing %s.",
                module_name,
            )
    return None
def _import_result_checker():
    """
    Пытаемся найти существующий result checker.
    Основной ожидаемый модуль:
        result_checker.py
    """
    try:
        return __import__(
            "result_checker"
        )
    except ImportError:
        return None
    except Exception:
        logger.exception(
            "Failed importing result_checker."
        )
        return None
# =========================================================
# SIGNAL WARNING
# =========================================================
async def warning_scheduler_loop() -> None:
    """
    Цикл предупреждений.
    Если в проекте есть собственный warning scheduler,
    используем его.
    Если нет — цикл просто остаётся активным и
    ничего не делает.
    Это позволяет scheduler.py работать независимо
    от наличия дополнительного warning-модуля.
    """
    logger.info(
        "Signal warning scheduler started."
    )
    module = _import_warning_components()
    callback = None
    if module is not None:
        # -------------------------------------------------
        # Возможные имена функции.
        # -------------------------------------------------
        for name in (
            "run_once",
            "check_warnings",
            "check_signal_warnings",
            "process_warnings",
            "warning_check",
        ):
            candidate = getattr(
                module,
                name,
                None,
            )
            if callable(candidate):
                callback = candidate
                break
    while _scheduler_running:
        try:
            if callback is not None:
                result = callback()
                if asyncio.iscoroutine(result):
                    await result
            try:
                await asyncio.wait_for(
                    _shutdown_event.wait(),
                    timeout=WARNING_INTERVAL,
                )
                break
            except asyncio.TimeoutError:
                pass
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Signal warning scheduler error."
            )
            try:
                await asyncio.wait_for(
                    _shutdown_event.wait(),
                    timeout=WARNING_INTERVAL,
                )
                break
            except asyncio.TimeoutError:
                pass
    logger.info(
        "Signal warning scheduler stopped."
    )
# =========================================================
# RESULT CHECKER
# =========================================================
async def result_checker_loop() -> None:
    """
    Проверяет завершившиеся сигналы.
    Основной вариант — использовать существующий
    result_checker.py.
    Если модуль отсутствует, цикл остаётся безопасным
    и не ломает приложение.
    """
    logger.info(
        "Result checker started."
    )
    module = _import_result_checker()
    callback = None
    if module is not None:
        # -------------------------------------------------
        # Возможные имена функции.
        # -------------------------------------------------
        for name in (
            "check_results",
            "check_signal_results",
            "resolve_signals",
            "resolve_pending_signals",
            "process_results",
            "run_once",
        ):
            candidate = getattr(
                module,
                name,
                None,
            )
            if callable(candidate):
                callback = candidate
                break
    while _scheduler_running:
        try:
            if callback is not None:
                result = callback()
                if asyncio.iscoroutine(result):
                    result = await result
                if isinstance(
                    result,
                    int,
                ):
                    logger.info(
                        "Resolved signals: %s",
                        result,
                    )
            else:
                logger.debug(
                    "Result checker callback not found."
                )
            try:
                await asyncio.wait_for(
                    _shutdown_event.wait(),
                    timeout=RESULT_CHECK_INTERVAL,
                )
                break
            except asyncio.TimeoutError:
                pass
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Result checker error."
            )
            try:
                await asyncio.wait_for(
                    _shutdown_event.wait(),
                    timeout=RESULT_CHECK_INTERVAL,
                )
                break
            except asyncio.TimeoutError:
                pass
    logger.info(
        "Result checker stopped."
    )
# =========================================================
# SIGNAL CALLBACK
# =========================================================
async def _send_signal_to_configured_destination(
    signal: Any,
) -> None:
    """
    Базовый callback для SignalScanner.
    ВАЖНО:
    Сам SignalScanner уже поддерживает send_signal.
    Поэтому scheduler не пытается напрямую отправлять
    сообщения в Telegram, если callback не был передан
    через configure_signal_sender().
    """
    sender = getattr(
        _send_signal_to_configured_destination,
        "_sender",
        None,
    )
    if sender is None:
        logger.warning(
            (
                "Signal found but Telegram "
                "signal sender is not configured | "
                "symbol=%s"
            ),
            getattr(
                signal,
                "symbol",
                "UNKNOWN",
            ),
        )
        return
    result = sender(
        signal
    )
    if asyncio.iscoroutine(result):
        await result
def configure_signal_sender(
    sender,
) -> None:
    """
    Устанавливает callback отправки сигналов.
    Например из main.py:
        configure_signal_sender(
            send_signal
        )
    После этого scheduler передаст callback
    в SignalScanner.
    """
    setattr(
        _send_signal_to_configured_destination,
        "_sender",
        sender,
    )
    logger.info(
        "Signal sender configured."
    )
# =========================================================
# CREATE SCANNER
# =========================================================
def _create_signal_scanner(
    market_client,
):
    """
    Создаёт текущий SignalScanner.
    Используются настройки самого signal_scanner.py:
        SIGNAL_SCAN_INTERVAL
        SIGNAL_CANDLE_LIMIT
        SIGNAL_MINIMUM_QUALITY
        SIGNAL_TIMEFRAMES
        SIGNAL_PAIRS_PER_CYCLE
        SIGNAL_COOLDOWN
        MARKET_SYMBOLS
    """
    SignalScanner = (
        _import_signal_scanner()
    )
    scanner = SignalScanner(
        market_client=market_client,
        send_signal=(
            _send_signal_to_configured_destination
        ),
    )
    logger.info(
        "SignalScanner class found."
    )
    logger.info(
        (
            "SignalScanner initialized "
            "using market_client=%s."
        ),
        type(
            market_client
        ).__name__,
    )
    return scanner
# =========================================================
# START SIGNAL GENERATION
# =========================================================
async def signal_generation_loop(
    market_client,
) -> None:
    """
    Запускает SignalScanner.
    Ключевой момент:
    НЕ создаём собственный бесконечный цикл здесь.
    SignalScanner.start() уже создаёт:
        SignalScanner._run_loop()
    который самостоятельно вызывает:
        scan_once()
    и ждёт:
        SIGNAL_SCAN_INTERVAL
    Поэтому здесь запускается ровно один scanner.
    """
    global _signal_scanner
    logger.info(
        "=============================================="
    )
    logger.info(
        "SIGNAL GENERATION LOOP STARTED"
    )
    logger.info(
        "=============================================="
    )
    if _signal_scanner is not None:
        logger.warning(
            "SignalScanner already exists."
        )
        return
    try:
        scanner = _create_signal_scanner(
            market_client
        )
        _signal_scanner = scanner
        logger.info(
            "Current SignalScanner selected."
        )
        logger.info(
            "=============================================="
        )
        logger.info(
            "SIGNAL SCANNER MODE"
        )
        logger.info(
            "=============================================="
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
            len(
                scanner.get_symbols()
            ),
            scanner.timeframes,
            scanner.scan_interval,
            scanner.candle_limit,
            scanner.minimum_quality,
        )
        # -------------------------------------------------
        # START INTERNAL SCANNER LOOP
        # -------------------------------------------------
        await scanner.start()
        logger.info(
            "SignalScanner started successfully."
        )
        # -------------------------------------------------
        # WAIT UNTIL SHUTDOWN
        # -------------------------------------------------
        while _scheduler_running:
            try:
                await asyncio.wait_for(
                    _shutdown_event.wait(),
                    timeout=5,
                )
                break
            except asyncio.TimeoutError:
                pass
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception(
            "Signal generation loop failed."
        )
    finally:
        scanner = _signal_scanner
        if scanner is not None:
            try:
                await scanner.stop()
            except Exception:
                logger.exception(
                    "Failed stopping SignalScanner."
                )
        _signal_scanner = None
        logger.info(
            "Signal generation loop stopped."
        )
# =========================================================
# START ALL
# =========================================================
async def start_scheduler(
    market_client,
) -> None:
    """
    Запускает всю автоматическую систему сигналов.
    Запускаются ровно 3 задачи:
        1. signal_generation
        2. signal_warning
        3. signal_result_checker
    SignalScanner внутри signal_generation имеет
    собственный цикл.
    """
    global _scheduler_running
    global _scheduler_tasks
    async with _start_lock:
        if _scheduler_running:
            logger.warning(
                "Scheduler already running."
            )
            return
        _scheduler_running = True
        _shutdown_event.clear()
        logger.info(
            "================================================"
        )
        logger.info(
            "STARTING TEYZUS SCHEDULER"
        )
        logger.info(
            "================================================"
        )
        # -------------------------------------------------
        # CREATE TASKS
        # -------------------------------------------------
        _scheduler_tasks = [
            asyncio.create_task(
                signal_generation_loop(
                    market_client
                ),
                name="signal_generation",
            ),
            asyncio.create_task(
                warning_scheduler_loop(),
                name="signal_warning",
            ),
            asyncio.create_task(
                result_checker_loop(),
                name="signal_result_checker",
            ),
        ]
        logger.info(
            "Scheduler started: %s tasks.",
            len(
                _scheduler_tasks
            ),
        )
        logger.info(
            "Scheduler tasks:"
        )
        logger.info(
            " - signal_generation"
        )
        logger.info(
            " - signal_warning"
        )
        logger.info(
            " - signal_result_checker"
        )
# =========================================================
# STOP ALL
# =========================================================
async def stop_scheduler() -> None:
    """
    Корректно останавливает scheduler и все его задачи.
    """
    global _scheduler_running
    global _scheduler_tasks
    global _signal_scanner
    async with _stop_lock:
        if not _scheduler_running:
            return
        logger.info(
            "Stopping TEYZUS scheduler..."
        )
        _scheduler_running = False
        _shutdown_event.set()
        # -------------------------------------------------
        # STOP SIGNAL SCANNER FIRST
        # -------------------------------------------------
        scanner = _signal_scanner
        if scanner is not None:
            try:
                await scanner.stop()
            except Exception:
                logger.exception(
                    "Error stopping SignalScanner."
                )
            _signal_scanner = None
        # -------------------------------------------------
        # CANCEL SCHEDULER TASKS
        # -------------------------------------------------
        tasks = list(
            _scheduler_tasks
        )
        _scheduler_tasks.clear()
        current_task = (
            asyncio.current_task()
        )
        for task in tasks:
            if (
                task is not current_task
                and not task.done()
            ):
                task.cancel()
        # -------------------------------------------------
        # WAIT TASKS
        # -------------------------------------------------
        if tasks:
            await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )
        logger.info(
            "TEYZUS scheduler stopped."
        )
# =========================================================
# STATUS
# =========================================================
def scheduler_running() -> bool:
    """
    Возвращает состояние scheduler.
    """
    return _scheduler_running
def get_signal_scanner():
    """
    Возвращает текущий SignalScanner.
    Может использоваться admin-панелью или
    статистикой.
    """
    return _signal_scanner
def get_scheduler_tasks() -> list[
    asyncio.Task[Any]
]:
    """
    Возвращает копию списка scheduler tasks.
    """
    return list(
        _scheduler_tasks
    )
# =========================================================
# COMPATIBILITY ALIASES
# =========================================================
# Если старый main.py использует другие названия,
# эти aliases позволяют не ломать существующий код.
async def start(
    market_client,
) -> None:
    await start_scheduler(
        market_client
    )
async def stop() -> None:
    await stop_scheduler()
async def start_scheduler_tasks(
    market_client,
) -> None:
    await start_scheduler(
        market_client
    )
async def stop_scheduler_tasks() -> None:
    await stop_scheduler()
# =========================================================
# EXPORTS
# =========================================================
__all__ = [
    "start_scheduler",
    "stop_scheduler",
    "start_scheduler_tasks",
    "stop_scheduler_tasks",
    "start",
    "stop",
    "configure_signal_sender",
    "signal_generation_loop",
    "warning_scheduler_loop",
    "result_checker_loop",
    "scheduler_running",
    "get_signal_scanner",
    "get_scheduler_tasks",
]
