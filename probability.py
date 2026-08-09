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

    def __init__(self) -> None:

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
            * 100
        )

    def get_probability(
        self,
        score: float,
        minimum_samples: int = 100,
    ) -> float | None:

        bucket = self._find_bucket(
            score
        )

        if bucket is None:
            return None

        if bucket.total < minimum_samples:
            return None

        return bucket.probability

    def get_statistics(
        self,
    ) -> list[ProbabilityBucket]:

        return [
            ProbabilityBucket(
                minimum_score=bucket.minimum_score,
                maximum_score=bucket.maximum_score,
                total=bucket.total,
                wins=bucket.wins,
                probability=bucket.probability,
            )
            for bucket in self.buckets
        ]

    def clear(self) -> None:

        for bucket in self.buckets:

            bucket.total = 0
            bucket.wins = 0
            bucket.probability = 0.0


probability_calibrator = (
    ProbabilityCalibrator()
)
