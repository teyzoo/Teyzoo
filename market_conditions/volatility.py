from __future__ import annotations

from market import Candle


def calculate_volatility(
    candles: list[Candle],
    period: int = 30,
) -> float:

    if len(candles) < 2:
        return 0.0

    candles = candles[-period:]

    values: list[float] = []

    for index in range(
        1,
        len(candles),
    ):

        previous = (
            candles[index - 1].close
        )

        current = (
            candles[index].close
        )

        if previous == 0:
            continue

        values.append(
            abs(
                current - previous
            )
            / previous
            * 100
        )

    if not values:
        return 0.0

    return (
        sum(values)
        / len(values)
    )
