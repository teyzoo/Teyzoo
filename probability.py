from __future__ import annotations

from dataclasses import dataclass


# ============================================================
# НАСТРОЙКИ
# ============================================================

# Минимальное количество исторических наблюдений
# внутри одного диапазона score.
MINIMUM_BUCKET_SAMPLES = 100

# Дополнительный запас для сглаживания.
#
# Это НЕ делает прогноз точнее само по себе.
# Он лишь не позволяет маленькой выборке
# превращаться в фальшивые 100%.
SMOOTHING_PRIOR = 10


# ============================================================
# PROBABILITY BUCKET
# ============================================================

@dataclass(slots=True)
class ProbabilityBucket:

    minimum_score: float

    maximum_score: float

    total: int = 0

    wins: int = 0

    probability: float = 0.0

    @property
    def losses(self) -> int:

        return max(
            0,
            self.total - self.wins,
        )

    @property
    def reliable(self) -> bool:

        return (
            self.total
            >= MINIMUM_BUCKET_SAMPLES
        )


# ============================================================
# PROBABILITY RESULT
# ============================================================

@dataclass(slots=True)
class ProbabilityResult:

    probability: float | None

    total_samples: int

    wins: int

    losses: int

    reliable: bool

    minimum_samples: int


# ============================================================
# CALIBRATOR
# ============================================================

class ProbabilityCalibrator:

    def __init__(self):

        self.buckets = [

            ProbabilityBucket(
                minimum_score=0,
                maximum_score=50,
            ),

            ProbabilityBucket(
                minimum_score=50,
                maximum_score=60,
            ),

            ProbabilityBucket(
                minimum_score=60,
                maximum_score=70,
            ),

            ProbabilityBucket(
                minimum_score=70,
                maximum_score=80,
            ),

            ProbabilityBucket(
                minimum_score=80,
                maximum_score=90,
            ),

            ProbabilityBucket(
                minimum_score=90,
                maximum_score=100.000001,
            ),
        ]

    # ========================================================
    # FIND BUCKET
    # ========================================================

    def _find_bucket(
        self,
        score: float,
    ) -> ProbabilityBucket | None:

        if score < 0:

            return None

        if score > 100:

            return None

        for bucket in self.buckets:

            if (
                bucket.minimum_score
                <= score
                < bucket.maximum_score
            ):

                return bucket

        return None

    # ========================================================
    # ADD RESULT
    # ========================================================

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

    # ========================================================
    # ADD MANY RESULTS
    # ========================================================

    def add_results(
        self,
        results: list[
            tuple[float, bool]
        ],
    ) -> None:

        for score, won in results:

            self.add_result(
                score=score,
                won=won,
            )

    # ========================================================
    # RAW PROBABILITY
    # ========================================================

    def get_raw_probability(
        self,
        score: float,
    ) -> float | None:

        bucket = self._find_bucket(
            score
        )

        if bucket is None:

            return None

        if bucket.total == 0:

            return None

        return (
            bucket.wins
            / bucket.total
            * 100.0
        )

    # ========================================================
    # SMOOTHED PROBABILITY
    # ========================================================

    def get_smoothed_probability(
        self,
        score: float,
    ) -> float | None:

        bucket = self._find_bucket(
            score
        )

        if bucket is None:

            return None

        if bucket.total == 0:

            return None

        # ----------------------------------------------------
        # Сглаживание.
        #
        # Используем нейтральный prior 50/50.
        # ----------------------------------------------------

        prior_wins = (
            SMOOTHING_PRIOR
            * 0.5
        )

        prior_total = (
            SMOOTHING_PRIOR
        )

        probability = (
            (
                bucket.wins
                + prior_wins
            )
            /
            (
                bucket.total
                + prior_total
            )
            * 100.0
        )

        return probability

    # ========================================================
    # PUBLIC RESULT
    # ========================================================

    def get_result(
        self,
        score: float,
    ) -> ProbabilityResult:

        bucket = self._find_bucket(
            score
        )

        if bucket is None:

            return ProbabilityResult(
                probability=None,
                total_samples=0,
                wins=0,
                losses=0,
                reliable=False,
                minimum_samples=(
                    MINIMUM_BUCKET_SAMPLES
                ),
            )

        if bucket.total == 0:

            return ProbabilityResult(
                probability=None,
                total_samples=0,
                wins=0,
                losses=0,
                reliable=False,
                minimum_samples=(
                    MINIMUM_BUCKET_SAMPLES
                ),
            )

        # ----------------------------------------------------
        # Недостаточная выборка
        # ----------------------------------------------------

        if (
            bucket.total
            < MINIMUM_BUCKET_SAMPLES
        ):

            return ProbabilityResult(
                probability=None,
                total_samples=(
                    bucket.total
                ),
                wins=bucket.wins,
                losses=bucket.losses,
                reliable=False,
                minimum_samples=(
                    MINIMUM_BUCKET_SAMPLES
                ),
            )

        probability = (
            self.get_smoothed_probability(
                score
            )
        )

        return ProbabilityResult(
            probability=probability,
            total_samples=(
                bucket.total
            ),
            wins=bucket.wins,
            losses=bucket.losses,
            reliable=True,
            minimum_samples=(
                MINIMUM_BUCKET_SAMPLES
            ),
        )

    # ========================================================
    # COMPATIBILITY METHOD
    # ========================================================

    def get_probability(
        self,
        score: float,
    ) -> float | None:

        result = self.get_result(
            score
        )

        if not result.reliable:

            return None

        return result.probability

    # ========================================================
    # BUCKET STATISTICS
    # ========================================================

    def get_bucket_statistics(
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
                    "losses": (
                        bucket.losses
                    ),
                    "probability": (
                        bucket.probability
                        if bucket.total
                        else None
                    ),
                    "reliable": (
                        bucket.reliable
                    ),
                }
            )

        return result

    # ========================================================
    # RESET
    # ========================================================

    def reset(self) -> None:

        for bucket in self.buckets:

            bucket.total = 0

            bucket.wins = 0

            bucket.probability = 0.0


# ============================================================
# SINGLETON
# ============================================================

probability_calibrator = (
    ProbabilityCalibrator()
)
