from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ProbabilityBucket:
    minimum_score: float
    maximum_score: float

    total: int
    wins: int

    probability: float


class ProbabilityCalibrator:

    def __init__(self):
        self.buckets = [
            ProbabilityBucket(
                minimum_score=50,
                maximum_score=60,
                total=0,
                wins=0,
                probability=0.0,
            ),
            ProbabilityBucket(
                minimum_score=60,
                maximum_score=70,
                total=0,
                wins=0,
                probability=0.0,
            ),
            ProbabilityBucket(
                minimum_score=70,
                maximum_score=80,
                total=0,
                wins=0,
                probability=0.0,
            ),
            ProbabilityBucket(
                minimum_score=80,
                maximum_score=90,
                total=0,
                wins=0,
                probability=0.0,
            ),
            ProbabilityBucket(
                minimum_score=90,
                maximum_score=101,
                total=0,
                wins=0,
                probability=0.0,
            ),
        ]

    def _find_bucket(
        self,
        score: float,
    ) -> ProbabilityBucket | None:

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
    ):

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
            * 100
        )

    def get_probability(
        self,
        score: float,
    ) -> float | None:

        bucket = self._find_bucket(
            score
        )

        if bucket is None:
            return None

        # Пока слишком мало истории —
        # не выдаём пользователю псевдовероятность.
        if bucket.total < 100:
            return None

        return bucket.probability


probability_calibrator = (
    ProbabilityCalibrator()
)
