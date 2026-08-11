from __future__ import annotations
from dataclasses import dataclass
from market import Candle
from models import Direction
from signal_engine import (
    AnalysisResult,
    signal_engine,
)
@dataclass(slots=True)
class Prediction:
    direction: Direction | None
    score: float
    confidence: float
    reasons: list[str]
class Predictor:
    def predict(
        self,
        candles: list[Candle],
    ) -> Prediction:
        result: AnalysisResult = (
            signal_engine.analyze(
                candles
            )
        )
        if result.direction is None:
            return Prediction(
                direction=None,
                score=0.0,
                confidence=0.0,
                reasons=result.reasons,
            )
        confidence = max(
            0.0,
            min(
                100.0,
                result.score,
            ),
        )
        return Prediction(
            direction=result.direction,
            score=result.score,
            confidence=confidence,
            reasons=result.reasons,
        )
predictor = Predictor()
