from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ProbabilityBucket:
    minimum_score: float
    maximum_score: float

    total: int = 0
    wins: int = 0

    @property
    def probability(self) -> float | None:

        if self.total == 0:
            return None

        return (
            self.wins
            / self.total
            * 100
        )


class ProbabilityCalibrator:

    def __init__(
        self,
        minimum_samples: int = 100,
    ):

        self.minimum_samples = (
            minimum_samples
        )

        self.buckets = [
            ProbabilityBucket(
                50,
                60,
            ),
            ProbabilityBucket(
                60,
                70,
            ),
            ProbabilityBucket(
                70,
                80,
            ),
            ProbabilityBucket(
                80,
                90,
            ),
            ProbabilityBucket(
                90,
                101,
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

        bucket = (
            self._find_bucket(
                score
            )
        )

        if bucket is None:
            return

        bucket.total += 1

        if won:
            bucket.wins += 1

    def get_probability(
        self,
        score: float,
    ) -> float | None:

        bucket = (
            self._find_bucket(
                score
            )
        )

        if bucket is None:
            return None

        if (
            bucket.total
            < self.minimum_samples
        ):
            return None

        return bucket.probability

    def get_statistics(
        self,
    ) -> list[dict]:

        result = []

        for bucket in self.buckets:

            result.append(
                {
                    "minimum_score": (
                        bucket.minimum_score
                    ),
                    "maximum_score": (
                        bucket.maximum_score
                    ),
                    "total": (
                        bucket.total
                    ),
                    "wins": (
                        bucket.wins
                    ),
                    "probability": (
                        bucket.probability
                    ),
                }
            )

        return result


probability_calibrator = (
    ProbabilityCalibrator()
)
