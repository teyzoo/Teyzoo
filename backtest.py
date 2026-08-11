from __future__ import annotations

from dataclasses import dataclass

from market import Candle
from signal_engine import signal_engine


@dataclass(slots=True)
class BacktestResult:
    total: int
    wins: int
    losses: int
    winrate: float
    skipped: int


def run_backtest(
    candles: list[Candle],
    lookback: int = 100,
    expiry_candles: int = 1,
) -> BacktestResult:
    lookback = max(
        20,
        int(lookback),
    )

    expiry_candles = max(
        1,
        int(expiry_candles),
    )

    if len(candles) <= (
        lookback + expiry_candles
    ):
        return BacktestResult(
            total=0,
            wins=0,
            losses=0,
            winrate=0.0,
            skipped=0,
        )

    wins = 0
    losses = 0
    skipped = 0

    last_index = (
        len(candles)
        - expiry_candles
    )

    for index in range(
        lookback,
        last_index,
    ):
        history = candles[
            : index + 1
        ]

        analysis = signal_engine.analyze(
            history
        )

        if analysis.direction is None:
            skipped += 1
            continue

        entry = float(
            candles[index].close
        )

        exit_price = float(
            candles[
                index + expiry_candles
            ].close
        )

        if analysis.direction.value == "UP":
            if exit_price > entry:
                wins += 1
            else:
                losses += 1

        elif analysis.direction.value == "DOWN":
            if exit_price < entry:
                wins += 1
            else:
                losses += 1

        else:
            skipped += 1

    total = (
        wins + losses
    )

    winrate = (
        wins / total * 100.0
        if total
        else 0.0
    )

    return BacktestResult(
        total=total,
        wins=wins,
        losses=losses,
        winrate=winrate,
        skipped=skipped,
    )


__all__ = [
    "BacktestResult",
    "run_backtest",
]
