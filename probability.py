from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ProbabilityBucket:
    minimum_score: float
    maximum_score: float

    total: int = 0
    wins: int = 0

    probability: float = 0.0


class ProbabilityCalibrator:
    """
    Историческая калибровка качества сигнала.

    ВАЖНО:

    probability != prediction.

    Это фактический исторический WINRATE
    для диапазона score.

    Пока накоплено мало данных,
    get_probability() возвращает None.
    """

    def __init__(
        self,
        minimum_samples: int = 100,
    ) -> None:
        self.minimum_samples = max(
            1,
            int(minimum_samples),
        )

        self.buckets = [
            ProbabilityBucket(50, 60),
            ProbabilityBucket(60, 70),
            ProbabilityBucket(70, 80),
            ProbabilityBucket(80, 90),
            ProbabilityBucket(90, 101),
        ]

    def _find_bucket(
        self,
        score: float,
    ) -> ProbabilityBucket | None:
        score = float(score)

        for bucket in self.buckets:
            if (
                bucket.minimum_score
                <= score
                < bucket.maximum_score
            ):
                return bucket

        return None

    def add_result(
        self,
        score: float,
        won: bool,
    ) -> None:
        bucket = self._find_bucket(
            score
        )

        if bucket is None:
            return

        bucket.total += 1

        if won:
            bucket.wins += 1

        bucket.probability = (
            bucket.wins
            / bucket.total
            * 100.0
        )

    def get_probability(
        self,
        score: float,
        minimum_samples: int | None = None,
    ) -> float | None:
        bucket = self._find_bucket(
            score
        )

        if bucket is None:
            return None

        required = (
            self.minimum_samples
            if minimum_samples is None
            else max(
                1,
                int(minimum_samples),
            )
        )

        if bucket.total < required:
            return None

        return bucket.probability

    def get_statistics(
        self,
    ) -> list[ProbabilityBucket]:
        return [
            ProbabilityBucket(
                minimum_score=b.minimum_score,
                maximum_score=b.maximum_score,
                total=b.total,
                wins=b.wins,
                probability=b.probability,
            )
            for b in self.buckets
        ]

    def clear(self) -> None:
        for bucket in self.buckets:
            bucket.total = 0
            bucket.wins = 0
            bucket.probability = 0.0


probability_calibrator = (
    ProbabilityCalibrator()
)


__all__ = [
    "ProbabilityBucket",
    "ProbabilityCalibrator",
    "probability_calibrator",
]
