from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable, Iterable

from market import (
    Candle,
    MarketClient,
    MarketDataError,
    MarketRateLimitError,
)
from models import Direction
from quality_filter import (
    QualityFilter,
    QualityResult,
    TimeframeAnalysis,
    analyze_timeframe,
)


logger = logging.getLogger("signal_scanner")


# =========================================================
# TYPES
# =========================================================


SignalCallback = Callable[
    ["TradingSignal"],
    Awaitable[None],
]


# =========================================================
# DATA MODELS
# =========================================================


@dataclass(slots=True)
class TradingSignal:
    """
    Готовый сигнал, который прошёл QualityFilter.

    Этот объект можно передать в Telegram handler,
    notification service или другой отправитель.
    """

    symbol: str
    direction: Direction
    quality_score: float

    confirmations: int
    total_checks: int

    timeframe_results: list[TimeframeAnalysis]

    reasons: list[str]
    created_at: datetime

    candle_timeframe: str = "5m"

    @property
    def direction_text(self) -> str:
        if self.direction == Direction.UP:
            return "UP"

        if self.direction == Direction.DOWN:
            return "DOWN"

        return str(self.direction)

    @property
    def quality_percent(self) -> float:
        return max(
            0.0,
            min(
                100.0,
                float(self.quality_score),
            ),
        )


@dataclass(slots=True)
class PairScanResult:
    """
    Результат анализа одной пары.

    Здесь может быть как сигнал,
    так и обычный rejected результат.
    """

    symbol: str

    accepted: bool

    quality_score: float

    direction: Direction | None

    confirmations: int

    total_checks: int

    timeframe_results: list[TimeframeAnalysis] = field(
        default_factory=list
    )

    reasons: list[str] = field(
        default_factory=list
    )

    rejected_reasons: list[str] = field(
        default_factory=list
    )

    error: str | None = None


@dataclass(slots=True)
class ScannerStatistics:
    """
    Статистика работы автоматического сканера.
    """

    cycles: int = 0

    pairs_seen: int = 0
    pairs_scanned: int = 0

    signals_found: int = 0
    signals_sent: int = 0

    rejected_signals: int = 0
    errors: int = 0

    started_at: float = field(
        default_factory=time.monotonic
    )

    last_cycle_started_at: datetime | None = None
    last_cycle_finished_at: datetime | None = None

    last_signal_at: datetime | None = None


# =========================================================
# SIGNAL SCANNER
# =========================================================


class SignalScanner:
    """
    Автоматический сканер торговых пар.

    Основной цикл:

        scanner.start()
             ↓
        каждые 5 минут
             ↓
        получить пары
             ↓
        анализировать пары
             ↓
        получить свечи
             ↓
        analyze_timeframe()
             ↓
        QualityFilter
             ↓
        если качество >= minimum_quality
             ↓
        callback(signal)

    =====================================================
    ВАЖНО
    =====================================================

    Сканер НЕ отправляет Telegram-сообщения напрямую.

    Вместо этого используется:

        on_signal(signal)

    В main.py можно подключить:

        async def send_signal(signal):
            await bot.send_message(...)

    Это позволяет не связывать scanner с aiogram.
    """

    def __init__(
        self,
        market_client: MarketClient,
        quality_filter: QualityFilter | None = None,
        symbols: Iterable[str] | None = None,
        timeframes: tuple[str, ...] = (
            "1m",
            "5m",
            "15m",
        ),
        candle_limit: int = 200,
        scan_interval: int = 300,
        minimum_quality: float = 85.0,
        minimum_confirmations: int = 2,
        max_concurrent_pairs: int = 2,
        on_signal: SignalCallback | None = None,
        signal_cooldown: int = 300,
    ) -> None:

        # =================================================
        # MARKET
        # =================================================

        self.market_client = market_client

        # =================================================
        # QUALITY
        # =================================================

        self.quality_filter = (
            quality_filter
            or QualityFilter(
                minimum_quality=minimum_quality
            )
        )

        self.minimum_quality = float(
            minimum_quality
        )

        self.minimum_confirmations = max(
            1,
            int(minimum_confirmations),
        )

        # =================================================
        # SYMBOLS
        # =================================================

        self._configured_symbols: list[str] = []

        if symbols is not None:
            self._configured_symbols = (
                self._normalize_symbols(
                    symbols
                )
            )

        # =================================================
        # TIMEFRAMES
        # =================================================

        if not timeframes:
            raise ValueError(
                "At least one timeframe is required."
            )

        self.timeframes = tuple(
            str(timeframe).strip()
            for timeframe in timeframes
            if str(timeframe).strip()
        )

        if not self.timeframes:
            raise ValueError(
                "At least one valid timeframe is required."
            )

        # =================================================
        # CANDLES
        # =================================================

        if candle_limit < 20:
            raise ValueError(
                "candle_limit must be at least 20."
            )

        if candle_limit > 5000:
            raise ValueError(
                "candle_limit cannot exceed 5000."
            )

        self.candle_limit = int(
            candle_limit
        )

        # =================================================
        # SCHEDULER
        # =================================================

        if scan_interval < 30:
            raise ValueError(
                "scan_interval must be at least 30 seconds."
            )

        self.scan_interval = int(
            scan_interval
        )

        # =================================================
        # CONCURRENCY
        # =================================================

        self.max_concurrent_pairs = max(
            1,
            int(max_concurrent_pairs),
        )

        self._pair_semaphore = asyncio.Semaphore(
            self.max_concurrent_pairs
        )

        # =================================================
        # CALLBACK
        # =================================================

        self.on_signal = on_signal

        # =================================================
        # DUPLICATE PROTECTION
        # =================================================

        self.signal_cooldown = max(
            0,
            int(signal_cooldown),
        )

        self._last_signal_times: dict[
            str,
            float,
        ] = {}

        self._signal_lock = asyncio.Lock()

        # =================================================
        # LOOP CONTROL
        # =================================================

        self._task: asyncio.Task[None] | None = None

        self._stop_event = asyncio.Event()

        self._running = False

        # =================================================
        # STATISTICS
        # =================================================

        self.statistics = ScannerStatistics()

        logger.info(
            (
                "SignalScanner initialized | "
                "timeframes=%s | "
                "candle_limit=%s | "
                "interval=%ss | "
                "min_quality=%.2f | "
                "min_confirmations=%s | "
                "concurrency=%s"
            ),
            self.timeframes,
            self.candle_limit,
            self.scan_interval,
            self.minimum_quality,
            self.minimum_confirmations,
            self.max_concurrent_pairs,
        )

    # =====================================================
    # NORMALIZE SYMBOLS
    # =====================================================

    @staticmethod
    def _normalize_symbols(
        symbols: Iterable[str],
    ) -> list[str]:

        result: list[str] = []

        seen: set[str] = set()

        for raw_symbol in symbols:

            symbol = (
                str(raw_symbol)
                .strip()
                .upper()
            )

            if not symbol:
                continue

            # ---------------------------------------------
            # EURUSD -> EUR/USD
            # ---------------------------------------------

            if (
                "/" not in symbol
                and len(symbol) == 6
                and symbol.isalpha()
            ):
                symbol = (
                    f"{symbol[:3]}/"
                    f"{symbol[3:]}"
                )

            if symbol in seen:
                continue

            seen.add(symbol)

            result.append(
                symbol
            )

        return result

    # =====================================================
    # GET SYMBOLS
    # =====================================================

    async def get_symbols(self) -> list[str]:
        """
        Получает список пар для сканирования.

        Приоритет:

        1. Если MarketProvider имеет
           get_available_symbols() —
           используем его.

        2. Иначе используем symbols,
           переданные в конструктор.

        3. Если ничего нет —
           возвращаем пустой список.
        """

        provider = (
            self.market_client.provider
        )

        # =================================================
        # DYNAMIC SYMBOL PROVIDER
        # =================================================

        method = getattr(
            provider,
            "get_available_symbols",
            None,
        )

        if callable(method):

            try:
                result = method()

                if asyncio.iscoroutine(result):
                    result = await result

                symbols = self._normalize_symbols(
                    result
                )

                if symbols:

                    logger.info(
                        (
                            "Loaded %s symbols "
                            "from market provider."
                        ),
                        len(symbols),
                    )

                    return symbols

            except Exception as exc:

                logger.exception(
                    (
                        "Could not load "
                        "available symbols "
                        "from market provider: %s"
                    ),
                    exc,
                )

        # =================================================
        # CONFIGURED SYMBOLS
        # =================================================

        symbols = list(
            self._configured_symbols
        )

        logger.info(
            (
                "Using configured symbols: "
                "%s"
            ),
            len(symbols),
        )

        return symbols

    # =====================================================
    # START
    # =====================================================

    async def start(
        self,
        immediate: bool = True,
    ) -> None:
        """
        Запускает автоматический scanner.

        immediate=True:

            сразу выполняется первый scan,

            потом следующий через interval.

        immediate=False:

            ждём первый interval.
        """

        if self._running:
            logger.warning(
                "SignalScanner is already running."
            )
            return

        self._running = True

        self._stop_event.clear()

        logger.info(
            "Starting automatic signal scanner."
        )

        self._task = asyncio.create_task(
            self._run_loop(),
            name="signal-scanner",
        )

        if not immediate:

            logger.info(
                (
                    "First scanner cycle "
                    "will start in %s seconds."
                ),
                self.scan_interval,
            )

    # =====================================================
    # STOP
    # =====================================================

    async def stop(self) -> None:

        if not self._running:

            logger.info(
                "SignalScanner is not running."
            )

            return

        logger.info(
            "Stopping automatic signal scanner."
        )

        self._running = False

        self._stop_event.set()

        task = self._task

        self._task = None

        if task is not None:

            try:
                await task

            except asyncio.CancelledError:
                pass

        logger.info(
            "Automatic signal scanner stopped."
        )

    # =====================================================
    # RUN LOOP
    # =====================================================

    async def _run_loop(self) -> None:

        first_cycle = True

        try:

            while not self._stop_event.is_set():

                # -----------------------------------------
                # WAIT BEFORE FIRST CYCLE
                # -----------------------------------------

                if (
                    first_cycle
                    and not self._should_run_immediately()
                ):
                    try:

                        await asyncio.wait_for(
                            self._stop_event.wait(),
                            timeout=self.scan_interval,
                        )

                    except asyncio.TimeoutError:
                        pass

                    if self._stop_event.is_set():
                        break

                first_cycle = False

                # -----------------------------------------
                # SCAN
                # -----------------------------------------

                cycle_started = time.monotonic()

                self.statistics.cycles += 1

                self.statistics.last_cycle_started_at = (
                    datetime.now(
                        timezone.utc
                    )
                )

                logger.info(
                    (
                        "========== "
                        "SCANNER CYCLE #%s START "
                        "=========="
                    ),
                    self.statistics.cycles,
                )

                try:

                    await self.scan_once()

                except asyncio.CancelledError:
                    raise

                except Exception as exc:

                    self.statistics.errors += 1

                    logger.exception(
                        (
                            "Unexpected scanner "
                            "cycle error: %s"
                        ),
                        exc,
                    )

                # -----------------------------------------
                # CYCLE FINISHED
                # -----------------------------------------

                self.statistics.last_cycle_finished_at = (
                    datetime.now(
                        timezone.utc
                    )
                )

                elapsed = (
                    time.monotonic()
                    - cycle_started
                )

                logger.info(
                    (
                        "========== "
                        "SCANNER CYCLE #%s END | "
                        "duration=%.2fs "
                        "=========="
                    ),
                    self.statistics.cycles,
                    elapsed,
                )

                # -----------------------------------------
                # WAIT UNTIL NEXT CYCLE
                # -----------------------------------------

                if self._stop_event.is_set():
                    break

                logger.info(
                    (
                        "Next scanner cycle "
                        "in %s seconds."
                    ),
                    self.scan_interval,
                )

                try:

                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self.scan_interval,
                    )

                except asyncio.TimeoutError:
                    pass

        except asyncio.CancelledError:

            logger.info(
                "Scanner loop cancelled."
            )

            raise

        finally:

            self._running = False

    # =====================================================
    # IMMEDIATE MODE
    # =====================================================

    def _should_run_immediately(self) -> bool:
        return True

    # =====================================================
    # SCAN ONCE
    # =====================================================

    async def scan_once(
        self,
    ) -> list[PairScanResult]:
        """
        Один полный цикл сканирования.

        Возвращает результаты всех пар.
        """

        symbols = await self.get_symbols()

        self.statistics.pairs_seen += len(
            symbols
        )

        if not symbols:

            logger.warning(
                (
                    "No market symbols "
                    "available for scanning."
                )
            )

            return []

        logger.info(
            (
                "Starting market scan: "
                "%s symbols."
            ),
            len(symbols),
        )

        # =================================================
        # CREATE TASKS
        # =================================================

        tasks = [
            asyncio.create_task(
                self.scan_pair(
                    symbol
                )
            )
            for symbol in symbols
        ]

        # =================================================
        # EXECUTE
        # =================================================

        raw_results = await asyncio.gather(
            *tasks,
            return_exceptions=True,
        )

        results: list[PairScanResult] = []

        # =================================================
        # PROCESS RESULTS
        # =================================================

        for symbol, result in zip(
            symbols,
            raw_results,
        ):

            if isinstance(
                result,
                asyncio.CancelledError,
            ):
                continue

            if isinstance(
                result,
                Exception,
            ):

                self.statistics.errors += 1

                logger.error(
                    (
                        "Unhandled pair scan "
                        "error for %s: %s"
                    ),
                    symbol,
                    result,
                )

                results.append(
                    PairScanResult(
                        symbol=symbol,
                        accepted=False,
                        quality_score=0.0,
                        direction=None,
                        confirmations=0,
                        total_checks=0,
                        rejected_reasons=[
                            str(result)
                        ],
                        error=str(result),
                    )
                )

                continue

            results.append(
                result
            )

        # =================================================
        # SUMMARY
        # =================================================

        accepted = [
            item
            for item in results
            if item.accepted
        ]

        rejected = [
            item
            for item in results
            if not item.accepted
        ]

        logger.info(
            (
                "Market scan completed | "
                "pairs=%s | "
                "accepted=%s | "
                "rejected=%s"
            ),
            len(results),
            len(accepted),
            len(rejected),
        )

        # =================================================
        # SORT SIGNALS BY QUALITY
        # =================================================

        accepted.sort(
            key=lambda item: (
                item.quality_score,
                item.confirmations,
            ),
            reverse=True,
        )

        if accepted:

            logger.info(
                "Top signals:"
            )

            for item in accepted[:10]:

                logger.info(
                    (
                        "SIGNAL | "
                        "%s | "
                        "%s | "
                        "quality=%.2f | "
                        "confirmations=%s/%s"
                    ),
                    item.symbol,
                    item.direction,
                    item.quality_score,
                    item.confirmations,
                    item.total_checks,
                )

        return results

    # =====================================================
    # SCAN PAIR
    # =====================================================

    async def scan_pair(
        self,
        symbol: str,
    ) -> PairScanResult:
        """
        Анализирует одну торговую пару.
        """

        symbol = (
            str(symbol)
            .strip()
            .upper()
        )

        if (
            "/" not in symbol
            and len(symbol) == 6
            and symbol.isalpha()
        ):
            symbol = (
                f"{symbol[:3]}/"
                f"{symbol[3:]}"
            )

        async with self._pair_semaphore:

            self.statistics.pairs_scanned += 1

            logger.info(
                (
                    "Scanning pair: "
                    "%s"
                ),
                symbol,
            )

            # =================================================
            # LOAD TIMEFRAMES
            # =================================================

            analyses: list[
                TimeframeAnalysis
            ] = []

            for timeframe in self.timeframes:

                if self._stop_event.is_set():
                    break

                try:

                    candles = (
                        await self.market_client.get_candles(
                            symbol=symbol,
                            timeframe=timeframe,
                            limit=self.candle_limit,
                        )
                    )

                except MarketRateLimitError as exc:

                    logger.warning(
                        (
                            "Rate limit while "
                            "scanning %s %s: %s"
                        ),
                        symbol,
                        timeframe,
                        exc,
                    )

                    return PairScanResult(
                        symbol=symbol,
                        accepted=False,
                        quality_score=0.0,
                        direction=None,
                        confirmations=0,
                        total_checks=len(
                            analyses
                        ),
                        timeframe_results=analyses,
                        rejected_reasons=[
                            (
                                "Market API "
                                "rate limit."
                            )
                        ],
                        error=str(exc),
                    )

                except (
                    MarketDataError,
                    ValueError,
                ) as exc:

                    logger.warning(
                        (
                            "Could not load "
                            "%s %s: %s"
                        ),
                        symbol,
                        timeframe,
                        exc,
                    )

                    continue

                except Exception as exc:

                    logger.exception(
                        (
                            "Unexpected candle "
                            "error for %s %s: %s"
                        ),
                        symbol,
                        timeframe,
                        exc,
                    )

                    continue

                # =================================================
                # ANALYZE TIMEFRAME
                # =================================================

                try:

                    analysis = (
                        analyze_timeframe(
                            timeframe=timeframe,
                            candles=candles,
                        )
                    )

                except Exception as exc:

                    logger.exception(
                        (
                            "Signal engine "
                            "error for %s %s: %s"
                        ),
                        symbol,
                        timeframe,
                    )

                    continue

                analyses.append(
                    analysis
                )

            # =================================================
            # NO DATA
            # =================================================

            if not analyses:

                logger.info(
                    (
                        "Pair rejected: "
                        "%s | "
                        "no timeframe analysis."
                    ),
                    symbol,
                )

                return PairScanResult(
                    symbol=symbol,
                    accepted=False,
                    quality_score=0.0,
                    direction=None,
                    confirmations=0,
                    total_checks=0,
                    timeframe_results=[],
                    rejected_reasons=[
                        (
                            "Не удалось получить "
                            "рыночные данные."
                        )
                    ],
                )

            # =================================================
            # QUALITY FILTER
            # =================================================

            try:

                quality = (
                    self.quality_filter.evaluate(
                        analyses
                    )
                )

            except Exception as exc:

                logger.exception(
                    (
                        "QualityFilter error "
                        "for %s: %s"
                    ),
                    symbol,
                    exc,
                )

                self.statistics.errors += 1

                return PairScanResult(
                    symbol=symbol,
                    accepted=False,
                    quality_score=0.0,
                    direction=None,
                    confirmations=0,
                    total_checks=len(
                        analyses
                    ),
                    timeframe_results=analyses,
                    rejected_reasons=[
                        (
                            "Ошибка анализа "
                            "качества сигнала."
                        )
                    ],
                    error=str(exc),
                )

            # =================================================
            # EXTRA CONFIRMATION CHECK
            # =================================================

            if (
                quality.confirmations
                < self.minimum_confirmations
            ):

                logger.info(
                    (
                        "Pair rejected: %s | "
                        "confirmations=%s < %s"
                    ),
                    symbol,
                    quality.confirmations,
                    self.minimum_confirmations,
                )

                rejected_reasons = list(
                    quality.rejected_reasons
                )

                rejected_reasons.append(
                    (
                        "Недостаточно подтверждений "
                        "по таймфреймам."
                    )
                )

                self.statistics.rejected_signals += 1

                return PairScanResult(
                    symbol=symbol,
                    accepted=False,
                    quality_score=quality.quality_score,
                    direction=None,
                    confirmations=quality.confirmations,
                    total_checks=quality.total_checks,
                    timeframe_results=quality.timeframe_results,
                    reasons=quality.reasons,
                    rejected_reasons=rejected_reasons,
                )

            # =================================================
            # EXTRA QUALITY CHECK
            # =================================================

            if (
                quality.quality_score
                < self.minimum_quality
            ):

                logger.info(
                    (
                        "Pair rejected: %s | "
                        "quality=%.2f < %.2f"
                    ),
                    symbol,
                    quality.quality_score,
                    self.minimum_quality,
                )

                rejected_reasons = list(
                    quality.rejected_reasons
                )

                if not rejected_reasons:

                    rejected_reasons.append(
                        (
                            "Качество ниже "
                            "минимального порога."
                        )
                    )

                self.statistics.rejected_signals += 1

                return PairScanResult(
                    symbol=symbol,
                    accepted=False,
                    quality_score=quality.quality_score,
                    direction=None,
                    confirmations=quality.confirmations,
                    total_checks=quality.total_checks,
                    timeframe_results=quality.timeframe_results,
                    reasons=quality.reasons,
                    rejected_reasons=rejected_reasons,
                )

            # =================================================
            # QUALITY FILTER REJECTED
            # =================================================

            if not quality.accepted:

                logger.info(
                    (
                        "Pair rejected by "
                        "QualityFilter: %s | "
                        "quality=%.2f | "
                        "reasons=%s"
                    ),
                    symbol,
                    quality.quality_score,
                    quality.rejected_reasons,
                )

                self.statistics.rejected_signals += 1

                return PairScanResult(
                    symbol=symbol,
                    accepted=False,
                    quality_score=quality.quality_score,
                    direction=None,
                    confirmations=quality.confirmations,
                    total_checks=quality.total_checks,
                    timeframe_results=quality.timeframe_results,
                    reasons=quality.reasons,
                    rejected_reasons=quality.rejected_reasons,
                )

            # =================================================
            # DIRECTION CHECK
            # =================================================

            if quality.direction is None:

                logger.info(
                    (
                        "Pair rejected: %s | "
                        "no final direction."
                    ),
                    symbol,
                )

                self.statistics.rejected_signals += 1

                return PairScanResult(
                    symbol=symbol,
                    accepted=False,
                    quality_score=quality.quality_score,
                    direction=None,
                    confirmations=quality.confirmations,
                    total_checks=quality.total_checks,
                    timeframe_results=quality.timeframe_results,
                    reasons=quality.reasons,
                    rejected_reasons=[
                        (
                            "Нет итогового "
                            "направления."
                        )
                    ],
                )

            # =================================================
            # DUPLICATE / COOLDOWN
            # =================================================

            can_send = (
                await self._can_send_signal(
                    symbol=symbol,
                    direction=quality.direction,
                )
            )

            if not can_send:

                logger.info(
                    (
                        "Pair has valid signal "
                        "but cooldown is active: "
                        "%s"
                    ),
                    symbol,
                )

                return PairScanResult(
                    symbol=symbol,
                    accepted=False,
                    quality_score=quality.quality_score,
                    direction=quality.direction,
                    confirmations=quality.confirmations,
                    total_checks=quality.total_checks,
                    timeframe_results=quality.timeframe_results,
                    reasons=quality.reasons,
                    rejected_reasons=[
                        (
                            "Сигнал по этой паре "
                            "уже недавно отправлялся."
                        )
                    ],
                )

            # =================================================
            # CREATE SIGNAL
            # =================================================

            signal = TradingSignal(
                symbol=symbol,
                direction=quality.direction,
                quality_score=quality.quality_score,
                confirmations=quality.confirmations,
                total_checks=quality.total_checks,
                timeframe_results=quality.timeframe_results,
                reasons=quality.reasons,
                created_at=datetime.now(
                    timezone.utc
                ),
                candle_timeframe=(
                    "5m"
                    if "5m" in self.timeframes
                    else self.timeframes[0]
                ),
            )

            # =================================================
            # REGISTER SIGNAL
            # =================================================

            await self._register_signal(
                signal
            )

            self.statistics.signals_found += 1

            self.statistics.last_signal_at = (
                signal.created_at
            )

            logger.info(
                (
                    "🔥 SIGNAL FOUND | "
                    "%s | "
                    "%s | "
                    "quality=%.2f | "
                    "confirmations=%s/%s"
                ),
                symbol,
                signal.direction,
                signal.quality_score,
                signal.confirmations,
                signal.total_checks,
            )

            # =================================================
            # CALLBACK
            # =================================================

            if self.on_signal is not None:

                try:

                    await self.on_signal(
                        signal
                    )

                    self.statistics.signals_sent += 1

                    logger.info(
                        (
                            "Signal callback "
                            "completed: %s"
                        ),
                        symbol,
                    )

                except asyncio.CancelledError:
                    raise

                except Exception as exc:

                    self.statistics.errors += 1

                    logger.exception(
                        (
                            "Signal callback "
                            "failed for %s: %s"
                        ),
                        symbol,
                        exc,
                    )

            return PairScanResult(
                symbol=symbol,
                accepted=True,
                quality_score=quality.quality_score,
                direction=quality.direction,
                confirmations=quality.confirmations,
                total_checks=quality.total_checks,
                timeframe_results=quality.timeframe_results,
                reasons=quality.reasons,
                rejected_reasons=[],
            )

    # =====================================================
    # CHECK SIGNAL COOLDOWN
    # =====================================================

    async def _can_send_signal(
        self,
        symbol: str,
        direction: Direction,
    ) -> bool:

        if self.signal_cooldown <= 0:
            return True

        key = (
            f"{symbol}:"
            f"{direction}"
        )

        now = time.monotonic()

        async with self._signal_lock:

            last_time = (
                self._last_signal_times.get(
                    key
                )
            )

            if last_time is None:
                return True

            elapsed = (
                now
                - last_time
            )

            if elapsed >= self.signal_cooldown:
                return True

            logger.debug(
                (
                    "Signal cooldown active | "
                    "symbol=%s | "
                    "direction=%s | "
                    "remaining=%.1fs"
                ),
                symbol,
                direction,
                self.signal_cooldown
                - elapsed,
            )

            return False

    # =====================================================
    # REGISTER SIGNAL
    # =====================================================

    async def _register_signal(
        self,
        signal: TradingSignal,
    ) -> None:

        if self.signal_cooldown <= 0:
            return

        key = (
            f"{signal.symbol}:"
            f"{signal.direction}"
        )

        async with self._signal_lock:

            self._last_signal_times[
                key
            ] = time.monotonic()

            # ---------------------------------------------
            # CLEAN OLD ENTRIES
            # ---------------------------------------------

            now = time.monotonic()

            expired = [
                key
                for key, timestamp
                in self._last_signal_times.items()
                if (
                    now - timestamp
                    > self.signal_cooldown * 3
                )
            ]

            for expired_key in expired:

                self._last_signal_times.pop(
                    expired_key,
                    None,
                )

    # =====================================================
    # FORMAT SIGNAL
    # =====================================================

    @staticmethod
    def format_signal(
        signal: TradingSignal,
    ) -> str:
        """
        Формирует готовый Telegram-текст.

        Можно использовать напрямую в main.py.
        """

        if signal.direction == Direction.UP:
            direction_text = "🟢 CALL / UP"

        elif signal.direction == Direction.DOWN:
            direction_text = "🔴 PUT / DOWN"

        else:
            direction_text = str(
                signal.direction
            )

        lines: list[str] = []

        lines.append(
            "🚨 НОВЫЙ СИГНАЛ"
        )

        lines.append("")

        lines.append(
            f"💱 Пара: {signal.symbol}"
        )

        lines.append(
            f"📊 Направление: {direction_text}"
        )

        lines.append(
            (
                f"⭐ Качество: "
                f"{signal.quality_percent:.1f}%"
            )
        )

        lines.append(
            (
                f"✅ Подтверждения: "
                f"{signal.confirmations}/"
                f"{signal.total_checks}"
            )
        )

        lines.append(
            (
                f"⏱ Таймфреймы: "
                f"{', '.join(self_timeframes(signal))}"
            )
        )

        if signal.reasons:

            lines.append("")

            lines.append(
                "📌 Подтверждения:"
            )

            unique_reasons: list[str] = []

            for reason in signal.reasons:

                text = str(
                    reason
                ).strip()

                if not text:
                    continue

                if text in unique_reasons:
                    continue

                unique_reasons.append(
                    text
                )

            for reason in unique_reasons[:10]:

                lines.append(
                    f"• {reason}"
                )

        lines.append("")

        lines.append(
            "⚠️ Сигнал прошёл автоматический "
            "фильтр качества."
        )

        return "\n".join(
            lines
        )

    # =====================================================
    # RUN SINGLE PAIR MANUALLY
    # =====================================================

    async def analyze_symbol(
        self,
        symbol: str,
    ) -> PairScanResult:

        return await self.scan_pair(
            symbol
        )

    # =====================================================
    # MANUAL SYMBOL UPDATE
    # =====================================================

    def set_symbols(
        self,
        symbols: Iterable[str],
    ) -> None:

        self._configured_symbols = (
            self._normalize_symbols(
                symbols
            )
        )

        logger.info(
            (
                "Scanner symbols updated: "
                "%s pairs."
            ),
            len(
                self._configured_symbols
            ),
        )

    # =====================================================
    # ADD SYMBOL
    # =====================================================

    def add_symbol(
        self,
        symbol: str,
    ) -> None:

        normalized = self._normalize_symbols(
            [symbol]
        )

        if not normalized:
            return

        for item in normalized:

            if item not in self._configured_symbols:

                self._configured_symbols.append(
                    item
                )

        logger.info(
            (
                "Symbol added to scanner: "
                "%s"
            ),
            normalized,
        )

    # =====================================================
    # REMOVE SYMBOL
    # =====================================================

    def remove_symbol(
        self,
        symbol: str,
    ) -> None:

        normalized = self._normalize_symbols(
            [symbol]
        )

        if not normalized:
            return

        target = normalized[0]

        self._configured_symbols = [
            item
            for item
            in self._configured_symbols
            if item != target
        ]

        logger.info(
            (
                "Symbol removed from scanner: "
                "%s"
            ),
            target,
        )

    # =====================================================
    # IS RUNNING
    # =====================================================

    @property
    def is_running(self) -> bool:
        return self._running

    # =====================================================
    # GET STATISTICS
    # =====================================================

    def get_statistics(
        self,
    ) -> ScannerStatistics:

        return ScannerStatistics(
            cycles=self.statistics.cycles,
            pairs_seen=self.statistics.pairs_seen,
            pairs_scanned=self.statistics.pairs_scanned,
            signals_found=self.statistics.signals_found,
            signals_sent=self.statistics.signals_sent,
            rejected_signals=self.statistics.rejected_signals,
            errors=self.statistics.errors,
            started_at=self.statistics.started_at,
            last_cycle_started_at=(
                self.statistics.last_cycle_started_at
            ),
            last_cycle_finished_at=(
                self.statistics.last_cycle_finished_at
            ),
            last_signal_at=(
                self.statistics.last_signal_at
            ),
        )


# =========================================================
# HELPERS
# =========================================================


def self_timeframes(
    signal: TradingSignal,
) -> list[str]:

    return [
        item.timeframe
        for item in signal.timeframe_results
        if item.direction == signal.direction
    ]


# =========================================================
# DEFAULT FOREX SYMBOLS
# =========================================================

DEFAULT_FOREX_SYMBOLS: tuple[str, ...] = (
    "EUR/USD",
    "GBP/USD",
    "USD/JPY",
    "USD/CHF",
    "AUD/USD",
    "USD/CAD",
    "NZD/USD",
    "EUR/GBP",
    "EUR/JPY",
    "GBP/JPY",
    "EUR/CHF",
    "GBP/CHF",
    "AUD/JPY",
    "CAD/JPY",
    "CHF/JPY",
    "EUR/AUD",
    "EUR/CAD",
    "EUR/NZD",
    "GBP/AUD",
    "GBP/CAD",
    "GBP/NZD",
    "AUD/CAD",
    "AUD/CHF",
    "AUD/NZD",
    "CAD/CHF",
    "NZD/JPY",
    "NZD/CAD",
    "NZD/CHF",
)


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "TradingSignal",
    "PairScanResult",
    "ScannerStatistics",
    "SignalScanner",
    "DEFAULT_FOREX_SYMBOLS",
]
