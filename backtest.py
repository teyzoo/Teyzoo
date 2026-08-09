from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from market import Candle
from models import Direction
from signal_engine import (
    SignalEngine,
)


# ============================================================
# НАСТРОЙКИ BACKTEST
# ============================================================

DEFAULT_EXPIRY_MINUTES = 1

# Не считаем статистику надёжной,
# пока не накопилось достаточно сделок.
MINIMUM_SAMPLE_SIZE = 100

# Минимальный технический score.
DEFAULT_MINIMUM_SCORE = 80.0


# ============================================================
# BACKTEST TRADE
# ============================================================

@dataclass(slots=True)
class BacktestTrade:

    entry_time: datetime

    expiry_time: datetime

    entry_price: float

    exit_price: float

    direction: Direction

    won: bool

    score: float


# ============================================================
# BACKTEST STATS
# ============================================================

@dataclass(slots=True)
class BacktestStats:

    total: int

    wins: int

    losses: int

    win_rate: float

    average_score: float

    max_consecutive_losses: int

    # Дополнительная статистика
    up_total: int

    up_wins: int

    up_win_rate: float

    down_total: int

    down_wins: int

    down_win_rate: float

    statistically_reliable: bool

    minimum_sample_size: int


# ============================================================
# EMPTY STATS
# ============================================================

def empty_stats() -> BacktestStats:

    return BacktestStats(
        total=0,
        wins=0,
        losses=0,
        win_rate=0.0,
        average_score=0.0,
        max_consecutive_losses=0,
        up_total=0,
        up_wins=0,
        up_win_rate=0.0,
        down_total=0,
        down_wins=0,
        down_win_rate=0.0,
        statistically_reliable=False,
        minimum_sample_size=(
            MINIMUM_SAMPLE_SIZE
        ),
    )


# ============================================================
# BACKTEST
# ============================================================

def run_backtest(
    candles: list[Candle],
    expiry_minutes: int = DEFAULT_EXPIRY_MINUTES,
    minimum_score: float = DEFAULT_MINIMUM_SCORE,
) -> tuple[
    list[BacktestTrade],
    BacktestStats,
]:

    trades: list[BacktestTrade] = []

    # --------------------------------------------------------
    # Проверяем входные данные
    # --------------------------------------------------------

    if not candles:

        return (
            trades,
            empty_stats(),
        )

    # Убираем возможные проблемы
    # с неправильным порядком свечей.
    candles = sorted(
        candles,
        key=lambda candle: candle.timestamp,
    )

    # Минимум данных для анализа.
    if len(candles) < 100:

        return (
            trades,
            empty_stats(),
        )

    # --------------------------------------------------------
    # Engine
    # --------------------------------------------------------

    engine = SignalEngine()

    expiry_delta = timedelta(
        minutes=expiry_minutes
    )

    # --------------------------------------------------------
    # Перебираем исторические точки
    # --------------------------------------------------------

    for index in range(
        100,
        len(candles),
    ):

        # История ДО момента входа.
        #
        # Будущее никогда не передаём
        # в SignalEngine.
        history = candles[
            : index + 1
        ]

        try:

            result = engine.analyze(
                history
            )

        except Exception:

            # Одна повреждённая точка
            # не должна ломать весь backtest.
            continue

        # ----------------------------------------------------
        # Нет сигнала
        # ----------------------------------------------------

        if result.direction is None:

            continue

        # ----------------------------------------------------
        # Сигнал был отклонён engine
        # ----------------------------------------------------

        if result.rejected:

            continue

        # ----------------------------------------------------
        # Проверяем score
        # ----------------------------------------------------

        if (
            result.score
            < minimum_score
        ):

            continue

        # ----------------------------------------------------
        # Точка входа
        # ----------------------------------------------------

        entry = candles[index]

        target_time = (
            entry.timestamp
            + expiry_delta
        )

        # ----------------------------------------------------
        # Ищем свечу на момент expiry
        # ----------------------------------------------------

        future = None

        for candidate in candles[
            index + 1 :
        ]:

            if (
                candidate.timestamp
                >= target_time
            ):

                future = candidate

                break

        if future is None:

            continue

        # ----------------------------------------------------
        # Цена
        # ----------------------------------------------------

        entry_price = (
            entry.close
        )

        exit_price = (
            future.close
        )

        # ----------------------------------------------------
        # Результат сделки
        # ----------------------------------------------------

        if (
            result.direction
            == Direction.UP
        ):

            won = (
                exit_price
                > entry_price
            )

        elif (
            result.direction
            == Direction.DOWN
        ):

            won = (
                exit_price
                < entry_price
            )

        else:

            continue

        # ----------------------------------------------------
        # Сохраняем сделку
        # ----------------------------------------------------

        trades.append(
            BacktestTrade(
                entry_time=(
                    entry.timestamp
                ),
                expiry_time=(
                    future.timestamp
                ),
                entry_price=(
                    entry_price
                ),
                exit_price=(
                    exit_price
                ),
                direction=(
                    result.direction
                ),
                won=won,
                score=(
                    result.score
                ),
            )
        )

    # ========================================================
    # СТАТИСТИКА
    # ========================================================

    total = len(trades)

    if total == 0:

        return (
            trades,
            empty_stats(),
        )

    # --------------------------------------------------------
    # Wins / losses
    # --------------------------------------------------------

    wins = sum(
        1
        for trade in trades
        if trade.won
    )

    losses = (
        total - wins
    )

    # --------------------------------------------------------
    # Win rate
    # --------------------------------------------------------

    win_rate = (
        wins
        / total
        * 100.0
    )

    # --------------------------------------------------------
    # Average score
    # --------------------------------------------------------

    average_score = (
        sum(
            trade.score
            for trade in trades
        )
        / total
    )

    # --------------------------------------------------------
    # Максимальная серия убытков
    # --------------------------------------------------------

    max_loss_streak = 0

    current_loss_streak = 0

    for trade in trades:

        if trade.won:

            current_loss_streak = 0

        else:

            current_loss_streak += 1

            max_loss_streak = max(
                max_loss_streak,
                current_loss_streak,
            )

    # --------------------------------------------------------
    # UP
    # --------------------------------------------------------

    up_trades = [
        trade
        for trade in trades
        if trade.direction
        == Direction.UP
    ]

    up_total = len(
        up_trades
    )

    up_wins = sum(
        1
        for trade in up_trades
        if trade.won
    )

    if up_total:

        up_win_rate = (
            up_wins
            / up_total
            * 100.0
        )

    else:

        up_win_rate = 0.0

    # --------------------------------------------------------
    # DOWN
    # --------------------------------------------------------

    down_trades = [
        trade
        for trade in trades
        if trade.direction
        == Direction.DOWN
    ]

    down_total = len(
        down_trades
    )

    down_wins = sum(
        1
        for trade in down_trades
        if trade.won
    )

    if down_total:

        down_win_rate = (
            down_wins
            / down_total
            * 100.0
        )

    else:

        down_win_rate = 0.0

    # --------------------------------------------------------
    # Надёжность статистики
    # --------------------------------------------------------

    statistically_reliable = (
        total
        >= MINIMUM_SAMPLE_SIZE
    )

    stats = BacktestStats(
        total=total,
        wins=wins,
        losses=losses,
        win_rate=win_rate,
        average_score=average_score,
        max_consecutive_losses=(
            max_loss_streak
        ),
        up_total=up_total,
        up_wins=up_wins,
        up_win_rate=up_win_rate,
        down_total=down_total,
        down_wins=down_wins,
        down_win_rate=down_win_rate,
        statistically_reliable=(
            statistically_reliable
        ),
        minimum_sample_size=(
            MINIMUM_SAMPLE_SIZE
        ),
    )

    return (
        trades,
        stats,
    )


# ============================================================
# ПРОВЕРКА НАДЁЖНОСТИ
# ============================================================

def is_backtest_reliable(
    stats: BacktestStats,
) -> bool:

    if stats.total < (
        stats.minimum_sample_size
    ):

        return False

    if stats.win_rate <= 50.0:

        return False

    return True


# ============================================================
# ТЕКСТОВОЕ ПРЕДСТАВЛЕНИЕ
# ============================================================

def format_backtest_stats(
    stats: BacktestStats,
) -> str:

    reliability = (
        "RELIABLE"
        if stats.statistically_reliable
        else "INSUFFICIENT DATA"
    )

    return (
        "Backtest statistics\n"
        "-------------------\n"
        f"Total: {stats.total}\n"
        f"Wins: {stats.wins}\n"
        f"Losses: {stats.losses}\n"
        f"Win rate: "
        f"{stats.win_rate:.2f}%\n"
        f"Average score: "
        f"{stats.average_score:.2f}%\n"
        f"Max losing streak: "
        f"{stats.max_consecutive_losses}\n"
        "\n"
        f"UP total: {stats.up_total}\n"
        f"UP wins: {stats.up_wins}\n"
        f"UP win rate: "
        f"{stats.up_win_rate:.2f}%\n"
        "\n"
        f"DOWN total: {stats.down_total}\n"
        f"DOWN wins: {stats.down_wins}\n"
        f"DOWN win rate: "
        f"{stats.down_win_rate:.2f}%\n"
        "\n"
        f"Reliability: {reliability}\n"
        f"Required sample: "
        f"{stats.minimum_sample_size}\n"
    )
