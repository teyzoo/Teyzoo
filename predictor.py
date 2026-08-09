from __future__ import annotations

from dataclasses import dataclass

from market import Candle
from models import Direction
from signal_engine import (
    SignalEngine,
)


@dataclass(slots=True)
class Prediction:
    direction: Direction | None
    score: float
    reasons: list[str]
    confirmations: int
    total_checks: int


class Predictor:

    def __init__(
        self,
        engine: SignalEngine | None = None,
    ):

        self.engine = (
            engine
            or SignalEngine()
        )

    def predict(
        self,
        candles: list[Candle],
    ) -> Prediction:

        result = self.engine.analyze(
            candles
        )

        return Prediction(
            direction=result.direction,
            score=result.score,
            reasons=result.reasons,
            confirmations=(
                result.confirmations
            ),
            total_checks=(
                result.total_checks
            ),
        )


predictor = Predictor()
