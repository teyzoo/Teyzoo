from __future__ import annotations
import asyncio
import logging
import os
from typing import Any
from aiogram import Bot
from market import MarketClient
from signal_scanner import (
    SignalScanner,
    TradingSignal,
)
logger = logging.getLogger("scheduler")
# =========================================================
# CONFIGURATION
# =========================================================
# Интервал проверки генерации сигналов.
#
# Сам SignalScanner также имеет свой интервал.
# Здесь этот параметр используется как защитный интервал
# между отдельными запусками generation loop.
#
SIGNAL_GENERATION_INTERVAL = max(
    10,
    int(
        os.getenv(
            "SCHEDULER_SIGNAL_GENERATION_INTERVAL",
            "300",
        )
    ),
)
# Предупреждение перед предполагаемым результатом сигнала.
#
# Например:
#
# сигнал появился в 12:00
# expiry = 5 минут
# warning = за 2 минуты
#
SIGNAL_WARNING_SECONDS = max(
    10,
    int(
        os.getenv(
            "SIGNAL_WARNING_SECONDS",
            "120",
        )
    ),
)
# Интервал проверки результатов.
#
# По умолчанию 15 секунд.
#
SIGNAL_RESULT_CHECK_INTERVAL = max(
    5,
    int(
        os.getenv(
            "SIGNAL_RESULT_CHECK_INTERVAL",
            "15",
        )
    ),
)
# Сколько минут живёт торговый сигнал.
#
# Это значение используется только scheduler-логикой
# для warning/result checker, если соответствующие модули
# поддерживают такой параметр.
#
SIGNAL_EXPIRY_MINUTES = max(
    1,
    int(
        os.getenv(
            "SIGNAL_EXPIRY_MINUTES",
            "5",
        )
    ),
)
# Telegram chat/channel, куда scheduler может отправлять
# найденные сигналы.
#
# Основной способ — SIGNAL_CHAT_ID.
#
# Если он не задан, scanner всё равно работает,
# но callback отправки не будет создан.
#
SIGNAL_CHAT_ID_RAW = os.getenv(
    "SIGNAL_CHAT_ID",
    "",
).strip()
# =========================================================
# OPTIONAL MODULES
# =========================================================
try:
    from signal_warning import (
        signal_warning,
    )
    SIGNAL_WARNING_AVAILABLE = True
except ImportError:
    signal_warning = None
    SIGNAL_WARNING_AVAILABLE = False
    logger.warning(
        "signal_warning module is not available."
    )
try:
    from signal_result_checker import (
        signal_result_checker,
    )
    SIGNAL_RESULT_CHECKER_AVAILABLE = True
except ImportError:
    signal_result_checker = None
    SIGNAL_RESULT_CHECKER_AVAILABLE = False
    logger.warning(
        "signal_result_checker module is not available."
    )
# =========================================================
# HELPERS
# =========================================================
def _parse_chat_id(
    value: str,
) -> int | str | None:
    """
    Преобразует SIGNAL_CHAT_ID.
    Поддерживает:
        123456789
        -1001234567890
        @channel
    """
    value = value.strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return value
def _safe_task_name(
    task: asyncio.Task[Any] | None,
) -> str:
    if task is None:
        return "unknown"
    try:
        return task.get_name()
    except Exception:
        return "unknown"
# =========================================================
# SCHEDULER
# =========================================================
class Scheduler:
    """
    Главный scheduler TEYZUS.
    Управляет тремя независимыми процессами:
        1. signal_generation
           SignalScanner:
               Market
                  ↓
             candles
                  ↓
           indicators
                  ↓
          quality_filter
                  ↓
             TradingSignal
                  ↓
              Telegram
        2. signal_warning
           Следит за активными сигналами и отправляет
           предупреждение перед окончанием срока.
        3. signal_result_checker
           Проверяет завершившиеся сигналы и определяет
           результат WIN / LOSS / DRAW.
    Ожидаемый API из main.py:
        scheduler = Scheduler(
            bot=bot,
            market=market,
        )
        await scheduler.start()
        ...
        await scheduler.stop()
    """
    def __init__(
        self,
        bot: Bot,
        market: MarketClient,
    ) -> None:
        # -------------------------------------------------
        # DEPENDENCIES
        # -------------------------------------------------
        self.bot = bot
        self.market = market
        # -------------------------------------------------
        # STATE
        # -------------------------------------------------
        self._running = False
        self._started = False
        self._stop_event = asyncio.Event()
        # -------------------------------------------------
        # TASKS
        # -------------------------------------------------
        self._signal_generation_task: (
            asyncio.Task[None] | None
        ) = None
        self._signal_warning_task: (
            asyncio.Task[None] | None
        ) = None
        self._signal_result_checker_task: (
            asyncio.Task[None] | None
        ) = None
        # -------------------------------------------------
        # SCANNER
        # -------------------------------------------------
        self.scanner: SignalScanner | None = None
        # -------------------------------------------------
        # SIGNAL STATE
        # -------------------------------------------------
        self._active_signals: dict[
            str,
            TradingSignal,
        ] = {}
        # -------------------------------------------------
        # STATISTICS
        # -------------------------------------------------
        self.generation_cycles = 0
        self.generated_signals = 0
        self.warning_cycles = 0
        self.result_checker_cycles = 0
        self.errors = 0
        logger.info(
            "Scheduler object created."
        )
    # =====================================================
    # START
    # =====================================================
    async def start(
        self,
    ) -> None:
        """
        Запускает scheduler.
        Безопасен при повторном вызове.
        """
        if self._started:
            logger.warning(
                "Scheduler is already started."
            )
            return
        logger.info(
            "================================================"
        )
        logger.info(
            "STARTING TEYZUS SCHEDULER"
        )
        logger.info(
            "================================================"
        )
        self._started = True
        self._running = True
        self._stop_event.clear()
        # -------------------------------------------------
        # CREATE SCANNER
        # -------------------------------------------------
        try:
            self.scanner = SignalScanner(
                market_client=self.market,
                send_signal=self._handle_signal,
            )
            logger.info(
                "SignalScanner initialized."
            )
        except Exception:
            self._running = False
            self._started = False
            logger.exception(
                "Failed to initialize SignalScanner."
            )
            raise
        # -------------------------------------------------
        # START TASKS
        # -------------------------------------------------
        self._signal_generation_task = (
            asyncio.create_task(
                self._signal_generation_loop(),
                name="signal_generation",
            )
        )
        self._signal_warning_task = (
            asyncio.create_task(
                self._signal_warning_loop(),
                name="signal_warning",
            )
        )
        self._signal_result_checker_task = (
            asyncio.create_task(
                self._signal_result_checker_loop(),
                name="signal_result_checker",
            )
        )
        logger.info(
            "Scheduler started: 3 tasks."
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
    # =====================================================
    # STOP
    # =====================================================
    async def stop(
        self,
    ) -> None:
        """
        Корректно останавливает все scheduler-задачи.
        """
        if not self._started:
            return
        logger.info(
            "Stopping TEYZUS scheduler..."
        )
        self._running = False
        self._stop_event.set()
        # -------------------------------------------------
        # STOP SIGNAL SCANNER
        # -------------------------------------------------
        if self.scanner is not None:
            try:
                await self.scanner.stop()
            except Exception:
                logger.exception(
                    "Error while stopping SignalScanner."
                )
        # -------------------------------------------------
        # COLLECT TASKS
        # -------------------------------------------------
        tasks: list[
            asyncio.Task[Any]
        ] = []
        for task in (
            self._signal_generation_task,
            self._signal_warning_task,
            self._signal_result_checker_task,
        ):
            if task is not None:
                tasks.append(task)
        # -------------------------------------------------
        # CANCEL
        # -------------------------------------------------
        for task in tasks:
            if not task.done():
                task.cancel()
        # -------------------------------------------------
        # WAIT
        # -------------------------------------------------
        if tasks:
            results = await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )
            for task, result in zip(
                tasks,
                results,
            ):
                if isinstance(
                    result,
                    Exception,
                ) and not isinstance(
                    result,
                    asyncio.CancelledError,
                ):
                    logger.error(
                        (
                            "Scheduler task %s "
                            "stopped with error: %s"
                        ),
                        _safe_task_name(task),
                        result,
                    )
        # -------------------------------------------------
        # RESET
        # -------------------------------------------------
        self._signal_generation_task = None
        self._signal_warning_task = None
        self._signal_result_checker_task = None
        self.scanner = None
        self._started = False
        logger.info(
            "TEYZUS scheduler stopped."
        )
    # =====================================================
    # SIGNAL GENERATION
    # =====================================================
    async def _signal_generation_loop(
        self,
    ) -> None:
        """
        Главный цикл генерации сигналов.
        ВАЖНО:
        Твой SignalScanner уже содержит собственный
        continuous loop.
        Поэтому scheduler НЕ создаёт второй бесконечный
        scanner loop.
        Scheduler запускает scanner.start() один раз.
        Это предотвращает двойной анализ рынка.
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
        scanner = self.scanner
        if scanner is None:
            logger.error(
                "SignalScanner is not initialized."
            )
            return
        try:
            # -------------------------------------------------
            # START CURRENT SIGNAL SCANNER
            # -------------------------------------------------
            await scanner.start()
            logger.info(
                "SignalScanner started."
            )
            # -------------------------------------------------
            # WAIT
            #
            # SignalScanner сам выполняет:
            #
            # scan_once()
            # ↓
            # wait
            # ↓
            # scan_once()
            #
            # Scheduler здесь только держит task живым.
            # -------------------------------------------------
            while self._running:
                self.generation_cycles += 1
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=SIGNAL_GENERATION_INTERVAL,
                    )
                    break
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            raise
        except Exception:
            self.errors += 1
            logger.exception(
                "Signal generation loop crashed."
            )
        finally:
            logger.info(
                "Signal generation loop stopped."
            )
    # =====================================================
    # HANDLE SIGNAL
    # =====================================================
    async def _handle_signal(
        self,
        signal: TradingSignal,
    ) -> None:
        """
        Callback, который получает сигнал
        непосредственно из SignalScanner.
        SignalScanner вызывает:
            await self._handle_signal(signal)
        """
        if not self._running:
            return
        self.generated_signals += 1
        # -------------------------------------------------
        # UNIQUE KEY
        # -------------------------------------------------
        key = self._signal_key(
            signal
        )
        self._active_signals[
            key
        ] = signal
        logger.info(
            (
                "================================================"
            )
        )
        logger.info(
            (
                "SIGNAL RECEIVED BY SCHEDULER | "
                "symbol=%s | "
                "direction=%s | "
                "quality=%.2f"
            ),
            signal.symbol,
            signal.direction,
            signal.quality_score,
        )
        logger.info(
            (
                "Signal active key=%s"
            ),
            key,
        )
        # -------------------------------------------------
        # TELEGRAM
        # -------------------------------------------------
        await self._send_signal_to_telegram(
            signal
        )
    # =====================================================
    # SIGNAL KEY
    # =====================================================
    @staticmethod
    def _signal_key(
        signal: TradingSignal,
    ) -> str:
        """
        Уникальный ключ сигнала.
        Включает:
            symbol
            direction
            created_at
        """
        created = signal.created_at
        return (
            f"{signal.symbol}:"
            f"{signal.direction}:"
            f"{created.timestamp():.0f}"
        )
    # =====================================================
    # TELEGRAM
    # =====================================================
    async def _send_signal_to_telegram(
        self,
        signal: TradingSignal,
    ) -> None:
        """
        Отправляет найденный сигнал в Telegram.
        Если SIGNAL_CHAT_ID не указан,
        сигнал всё равно считается найденным,
        но Telegram отправка пропускается.
        """
        chat_id = _parse_chat_id(
            SIGNAL_CHAT_ID_RAW
        )
        if chat_id is None:
            logger.warning(
                (
                    "SIGNAL_CHAT_ID is not configured. "
                    "Signal will not be sent to Telegram: %s"
                ),
                signal.symbol,
            )
            return
        try:
            text = (
                SignalScanner.format_signal(
                    signal
                )
            )
            await self.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
            )
            logger.info(
                (
                    "Signal sent to Telegram | "
                    "symbol=%s | "
                    "direction=%s | "
                    "quality=%.2f"
                ),
                signal.symbol,
                signal.direction,
                signal.quality_score,
            )
        except Exception:
            self.errors += 1
            logger.exception(
                (
                    "Failed to send signal "
                    "to Telegram | symbol=%s"
                ),
                signal.symbol,
            )
    # =====================================================
    # WARNING LOOP
    # =====================================================
    async def _signal_warning_loop(
        self,
    ) -> None:
        """
        Цикл предупреждений.
        Если signal_warning.py существует,
        передаём управление ему.
        Поддерживаются разные версии API модуля,
        чтобы scheduler не падал из-за небольшого
        изменения сигнатуры.
        """
        logger.info(
            "Signal warning scheduler started."
        )
        if not SIGNAL_WARNING_AVAILABLE:
            logger.info(
                (
                    "signal_warning.py is not available. "
                    "Warning scheduler is idle."
                )
            )
        try:
            while self._running:
                self.warning_cycles += 1
                # -------------------------------------------------
                # EXTERNAL WARNING FUNCTION
                # -------------------------------------------------
                if (
                    SIGNAL_WARNING_AVAILABLE
                    and signal_warning is not None
                ):
                    try:
                        await self._call_warning_function()
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        self.errors += 1
                        logger.exception(
                            "Signal warning cycle failed."
                        )
                # -------------------------------------------------
                # WAIT
                # -------------------------------------------------
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=15,
                    )
                    break
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            raise
        finally:
            logger.info(
                "Signal warning scheduler stopped."
            )
    # =====================================================
    # CALL WARNING FUNCTION
    # =====================================================
    async def _call_warning_function(
        self,
    ) -> None:
        """
        Универсальный вызов signal_warning().
        Основной ожидаемый вариант:
            signal_warning(
                bot=self.bot,
                market=self.market,
            )
        Если текущий модуль принимает только bot/market,
        используется соответствующая сигнатура.
        Ошибка TypeError не ломает scheduler.
        """
        if signal_warning is None:
            return
        function = signal_warning
        # -------------------------------------------------
        # FIRST
        # -------------------------------------------------
        try:
            result = function(
                bot=self.bot,
                market=self.market,
            )
            if asyncio.iscoroutine(result):
                await result
            return
        except TypeError:
            pass
        # -------------------------------------------------
        # SECOND
        # -------------------------------------------------
        try:
            result = function(
                bot=self.bot,
            )
            if asyncio.iscoroutine(result):
                await result
            return
        except TypeError:
            pass
        # -------------------------------------------------
        # THIRD
        # -------------------------------------------------
        try:
            result = function(
                market=self.market,
            )
            if asyncio.iscoroutine(result):
                await result
            return
        except TypeError:
            pass
        # -------------------------------------------------
        # FOURTH
        # -------------------------------------------------
        try:
            result = function()
            if asyncio.iscoroutine(result):
                await result
        except TypeError as exc:
            logger.warning(
                (
                    "signal_warning() has unsupported "
                    "signature: %s"
                ),
                exc,
            )
    # =====================================================
    # RESULT CHECKER LOOP
    # =====================================================
    async def _signal_result_checker_loop(
        self,
    ) -> None:
        """
        Цикл проверки результатов сигналов.
        Основной модуль:
            signal_result_checker.py
        Scheduler не выполняет собственную торговую
        логику результата, если отдельный checker
        уже существует.
        """
        logger.info(
            "Result checker started."
        )
        if not SIGNAL_RESULT_CHECKER_AVAILABLE:
            logger.info(
                (
                    "signal_result_checker.py "
                    "is not available. "
                    "Result checker is idle."
                )
            )
        try:
            while self._running:
                self.result_checker_cycles += 1
                # -------------------------------------------------
                # EXTERNAL RESULT CHECKER
                # -------------------------------------------------
                if (
                    SIGNAL_RESULT_CHECKER_AVAILABLE
                    and signal_result_checker is not None
                ):
                    try:
                        await self._call_result_checker()
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        self.errors += 1
                        logger.exception(
                            "Result checker cycle failed."
                        )
                # -------------------------------------------------
                # CLEAN LOCAL ACTIVE SIGNALS
                # -------------------------------------------------
                self._cleanup_old_signals()
                # -------------------------------------------------
                # WAIT
                # -------------------------------------------------
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=SIGNAL_RESULT_CHECK_INTERVAL,
                    )
                    break
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            raise
        finally:
            logger.info(
                "Result checker stopped."
            )
    # =====================================================
    # CALL RESULT CHECKER
    # =====================================================
    async def _call_result_checker(
        self,
    ) -> None:
        """
        Универсальный вызов result checker.
        Основной вариант:
            signal_result_checker(
                bot=self.bot,
                market=self.market,
            )
        Поддерживаются несколько вариантов сигнатуры.
        """
        if signal_result_checker is None:
            return
        function = signal_result_checker
        # -------------------------------------------------
        # FIRST
        # -------------------------------------------------
        try:
            result = function(
                bot=self.bot,
                market=self.market,
            )
            if asyncio.iscoroutine(result):
                await result
            return
        except TypeError:
            pass
        # -------------------------------------------------
        # SECOND
        # -------------------------------------------------
        try:
            result = function(
                market=self.market,
            )
            if asyncio.iscoroutine(result):
                await result
            return
        except TypeError:
            pass
        # -------------------------------------------------
        # THIRD
        # -------------------------------------------------
        try:
            result = function(
                bot=self.bot,
            )
            if asyncio.iscoroutine(result):
                await result
            return
        except TypeError:
            pass
        # -------------------------------------------------
        # FOURTH
        # -------------------------------------------------
        try:
            result = function()
            if asyncio.iscoroutine(result):
                await result
        except TypeError as exc:
            logger.warning(
                (
                    "signal_result_checker() has "
                    "unsupported signature: %s"
                ),
                exc,
            )
    # =====================================================
    # CLEAN OLD SIGNALS
    # =====================================================
    def _cleanup_old_signals(
        self,
    ) -> None:
        """
        Удаляет старые сигналы из локального memory cache.
        Это НЕ заменяет базу данных.
        Он нужен только для того, чтобы scheduler
        не держал бесконечно растущий dict.
        """
        if not self._active_signals:
            return
        now = (
            asyncio.get_running_loop().time()
        )
        max_age = (
            SIGNAL_EXPIRY_MINUTES * 60
            + SIGNAL_WARNING_SECONDS
            + 60
        )
        expired: list[str] = []
        for key, signal in (
            self._active_signals.items()
        ):
            try:
                created_timestamp = (
                    signal.created_at.timestamp()
                )
                current_timestamp = (
                    __import__(
                        "time"
                    ).time()
                )
                age = (
                    current_timestamp
                    - created_timestamp
                )
                if age > max_age:
                    expired.append(
                        key
                    )
            except Exception:
                expired.append(
                    key
                )
        for key in expired:
            self._active_signals.pop(
                key,
                None,
            )
        if expired:
            logger.debug(
                (
                    "Cleaned %s expired "
                    "signals from scheduler cache."
                ),
                len(expired),
            )
    # =====================================================
    # MANUAL SCAN
    # =====================================================
    async def scan_now(
        self,
    ) -> list[TradingSignal]:
        """
        Ручной запуск одного scan_once().
        Можно использовать из admin panel.
        Например:
            await scheduler.scan_now()
        """
        if not self._running:
            raise RuntimeError(
                "Scheduler is not running."
            )
        if self.scanner is None:
            raise RuntimeError(
                "SignalScanner is not initialized."
            )
        logger.info(
            "Manual signal scan requested."
        )
        return await self.scanner.scan_once()
    # =====================================================
    # STATUS
    # =====================================================
    @property
    def running(
        self,
    ) -> bool:
        return self._running
    @property
    def started(
        self,
    ) -> bool:
        return self._started
    # =====================================================
    # GET SCANNER
    # =====================================================
    def get_scanner(
        self,
    ) -> SignalScanner | None:
        return self.scanner
    # =====================================================
    # GET ACTIVE SIGNALS
    # =====================================================
    def get_active_signals(
        self,
    ) -> list[TradingSignal]:
        return list(
            self._active_signals.values()
        )
    # =====================================================
    # GET STATISTICS
    # =====================================================
    def get_stats(
        self,
    ) -> dict[str, Any]:
        scanner_stats = None
        if self.scanner is not None:
            try:
                scanner_stats = (
                    self.scanner.get_stats()
                )
            except Exception:
                scanner_stats = None
        return {
            "running": self._running,
            "started": self._started,
            "generation_cycles": (
                self.generation_cycles
            ),
            "generated_signals": (
                self.generated_signals
            ),
            "warning_cycles": (
                self.warning_cycles
            ),
            "result_checker_cycles": (
                self.result_checker_cycles
            ),
            "errors": self.errors,
            "active_signals": (
                len(
                    self._active_signals
                )
            ),
            "scanner": scanner_stats,
        }
# =========================================================
# FACTORY
# =========================================================
def create_scheduler(
    bot: Bot,
    market: MarketClient,
) -> Scheduler:
    """
    Factory для создания Scheduler.
    """
    return Scheduler(
        bot=bot,
        market=market,
    )
# =========================================================
# EXPORTS
# =========================================================
__all__ = [
    "Scheduler",
    "create_scheduler",
]
