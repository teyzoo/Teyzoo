from __future__ import annotations

from dataclasses import dataclass

from market import Candle
from models import Direction
from signal_engine import AnalysisResult, signal_engine


@dataclass(slots=True)
class Prediction:
    direction: Direction | None
    score: float
    confidence: float
    reasons: list[str]

    @property
    def is_actionable(self) -> bool:
        return self.direction is not None and self.score > 0.0


class Predictor:
    """
    Единая точка получения прогноза из SignalEngine.

    Predictor НЕ придумывает собственный сигнал.
    Он только нормализует результат SignalEngine.

    Это важно, чтобы:
        signal_engine
        predictor
        quality_filter
        signal_generator

    не рассчитывали разные score независимо друг от друга.
    """

    def __init__(
        self,
        engine=signal_engine,
    ) -> None:
        self.engine = engine

    def predict(
        self,
        candles: list[Candle],
    ) -> Prediction:
        if not candles:
            return Prediction(
                direction=None,
                score=0.0,
                confidence=0.0,
                reasons=[
                    "Нет свечей для прогноза."
                ],
            )

        try:
            result: AnalysisResult = (
                self.engine.analyze(candles)
            )
        except Exception as exc:
            return Prediction(
                direction=None,
                score=0.0,
                confidence=0.0,
                reasons=[
                    f"Ошибка Predictor: {exc}"
                ],
            )

        score = self._normalize_score(
            result.score
        )

        if result.direction is None:
            return Prediction(
                direction=None,
                score=0.0,
                confidence=0.0,
                reasons=list(result.reasons),
            )

        return Prediction(
            direction=result.direction,
            score=score,
            confidence=score,
            reasons=list(result.reasons),
        )

    @staticmethod
    def _normalize_score(
        score: float,
    ) -> float:
        try:
            value = float(score)
        except (
            TypeError,
            ValueError,
        ):
            return 0.0

        if value != value:
            return 0.0

        return max(
            0.0,
            min(
                100.0,
                value,
            ),
        )


predictor = Predictor()


__all__ = [
    "Prediction",
    "Predictor",
    "predictor",
]
