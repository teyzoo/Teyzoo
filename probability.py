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
                50,
                60,
                0,
                0,
                0.0,
            ),
            ProbabilityBucket(
                60,
                70,
                0,
                0,
                0.0,
            ),
            ProbabilityBucket(
                70,
                80,
                0,
                0,
                0.0,
            ),
            ProbabilityBucket(
                80,
                90,
                0,
                0,
                0.0,
            ),
            ProbabilityBucket(
                90,
                101,
                0,
                0,
                0.0,
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
    ) -> float | None:

        bucket = self._find_bucket(
            score
        )

        if bucket is None:
            return None

        if bucket.total < 100:
            return None

        return bucket.probability


probability_calibrator = (
    ProbabilityCalibrator()
)
