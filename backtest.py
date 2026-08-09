from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from indicators import (
    calculate_indicators,
)

from market import Candle

from models import Direction


@dataclass(slots=True)
class BacktestTrade:

    entry_time: datetime

    expiry_time: datetime

    entry_price: float

    exit_price: float

    direction: Direction

    won: bool

    score: float


@dataclass(slots=True)
class BacktestStats:

    total: int

    wins: int

    losses: int

    win_rate: float

    average_score: float

    max_consecutive_losses: int


def calculate_direction(
    candles: list[Candle],
) -> tuple[
    Direction | None,
    float,
]:

    if len(candles) < 50:
        return None, 0.0

    indicators = (
        calculate_indicators(
            candles
        )
    )

    bullish = 0
    bearish = 0

    checks = 0

    if (
        indicators.ema_fast
        is not None
        and indicators.ema_slow
        is not None
    ):

        checks += 1

        if (
            indicators.ema_fast
            > indicators.ema_slow
        ):

            bullish += 1

        elif (
            indicators.ema_fast
            < indicators.ema_slow
        ):

            bearish += 1

    if (
        indicators.macd
        is not None
        and indicators.macd_signal
        is not None
    ):

        checks += 1

        if (
            indicators.macd
            > indicators.macd_signal
        ):

            bullish += 1

        elif (
            indicators.macd
            < indicators.macd_signal
        ):

            bearish += 1

    if indicators.rsi is not None:

        checks += 1

        if indicators.rsi < 35:
            bullish += 1

        elif indicators.rsi > 65:
            bearish += 1

    if (
        indicators.bollinger_upper
        is not None
        and indicators.bollinger_lower
        is not None
    ):

        checks += 1

        if (
            indicators.price
            <= indicators.bollinger_lower
        ):

            bullish += 1

        elif (
            indicators.price
            >= indicators.bollinger_upper
        ):

            bearish += 1

    if checks == 0:
        return None, 0.0

    if bullish == bearish:
        return None, 0.0

    if bullish > bearish:

        return (
            Direction.UP,
            bullish
            / checks
            * 100,
        )

    return (
        Direction.DOWN,
        bearish
        / checks
        * 100,
    )


def run_backtest(
    candles: list[Candle],
    expiry_minutes: int = 1,
    minimum_score: float = 85.0,
) -> tuple[
    list[BacktestTrade],
    BacktestStats,
]:

    trades: list[
        BacktestTrade
    ] = []

    if len(candles) < 60:

        return (
            trades,
            BacktestStats(
                total=0,
                wins=0,
                losses=0,
                win_rate=0.0,
                average_score=0.0,
                max_consecutive_losses=0,
            ),
        )

    expiry_delta = timedelta(
        minutes=expiry_minutes
    )

    for index in range(
        50,
        len(candles),
    ):

        history = candles[
            :index + 1
        ]

        direction, score = (
            calculate_direction(
                history
            )
        )

        if direction is None:
            continue

        if score < minimum_score:
            continue

        entry = candles[index]

        target_time = (
            entry.timestamp
            + expiry_delta
        )

        future = None

        for candidate in candles[
            index + 1:
        ]:

            if (
                candidate.timestamp
                >= target_time
            ):

                future = candidate
                break

        if future is None:
            continue

        entry_price = (
            entry.close
        )

        exit_price = (
            future.close
        )

        if direction == Direction.UP:

            won = (
                exit_price
                > entry_price
            )

        else:

            won = (
                exit_price
                < entry_price
            )

        trades.append(
            BacktestTrade(
                entry_time=entry.timestamp,
                expiry_time=future.timestamp,
                entry_price=entry_price,
                exit_price=exit_price,
                direction=direction,
                won=won,
                score=score,
            )
        )

    total = len(trades)

    wins = sum(
        trade.won
        for trade in trades
    )

    losses = (
        total - wins
    )

    win_rate = (
        wins / total * 100
        if total
        else 0.0
    )

    average_score = (
        sum(
            trade.score
            for trade in trades
        )
        / total
        if total
        else 0.0
    )

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

    stats = BacktestStats(
        total=total,
        wins=wins,
        losses=losses,
        win_rate=win_rate,
        average_score=average_score,
        max_consecutive_losses=(
            max_loss_streak
        ),
    )

    return trades, stats
