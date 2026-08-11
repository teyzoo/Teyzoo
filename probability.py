from __future__ import annotations

from dataclasses import dataclass
from threading import RLock


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


class ProbabilityCalibrator:
    """
    Историческая калибровка score.

    ВАЖНО:

    score != гарантированная вероятность.

    Вероятность появляется только после накопления
    реальных результатов сигналов.

    Для маленького количества наблюдений используется
    сглаженная оценка вместо возврата 0%.
    """

    DEFAULT_BUCKETS = (
        (50.0, 60.0),
        (60.0, 70.0),
        (70.0, 80.0),
        (80.0, 90.0),
        (90.0, 101.0),
    )

    def __init__(
        self,
        minimum_samples: int = 10,
        prior_probability: float = 50.0,
        prior_strength: float = 4.0,
    ) -> None:
        self.minimum_samples = max(
            1,
            int(minimum_samples),
        )

        self.prior_probability = max(
            0.0,
            min(
                100.0,
                float(prior_probability),
            ),
        )

        self.prior_strength = max(
            0.0,
            float(prior_strength),
        )

        self._lock = RLock()

        self.buckets = [
            ProbabilityBucket(
                minimum_score=minimum,
                maximum_score=maximum,
            )
            for minimum, maximum
            in self.DEFAULT_BUCKETS
        ]

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

        return max(
            0.0,
            min(
                100.0,
                value,
            ),
        )

    def _find_bucket(
        self,
        score: float,
    ) -> ProbabilityBucket | None:
        value = self._normalize_score(
            score
        )

        for bucket in self.buckets:
            if (
                bucket.minimum_score
                <= value
                < bucket.maximum_score
            ):
                return bucket

        if value >= 100.0:
            return self.buckets[-1]

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

        with self._lock:
            bucket.total += 1

            if bool(won):
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
        """
        Возвращает историческую вероятность.

        Если наблюдений мало, возвращает сглаженную
        оценку только если minimum_samples достигнут.

        Это защищает SignalPolicy от использования
        случайного результата на 1-2 наблюдениях.
        """

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

        with self._lock:
            if bucket.total < required:
                return None

            wins = float(bucket.wins)
            total = float(bucket.total)

            numerator = (
                wins
                + (
                    self.prior_probability
                    / 100.0
                )
                * self.prior_strength
            )

            denominator = (
                total
                + self.prior_strength
            )

            if denominator <= 0:
                return None

            return max(
                0.0,
                min(
                    100.0,
                    numerator
                    / denominator
                    * 100.0,
                ),
            )

    def get_smoothed_probability(
        self,
        score: float,
    ) -> float | None:
        """
        Возвращает сглаженную вероятность даже
        при недостатке истории.

        Использовать для отображения статистики,
        но не обязательно для допуска сигнала.
        """

        bucket = self._find_bucket(
            score
        )

        if bucket is None:
            return None

        with self._lock:
            numerator = (
                bucket.wins
                + (
                    self.prior_probability
                    / 100.0
                )
                * self.prior_strength
            )

            denominator = (
                bucket.total
                + self.prior_strength
            )

            if denominator <= 0:
                return None

            return max(
                0.0,
                min(
                    100.0,
                    numerator
                    / denominator
                    * 100.0,
                ),
            )

    def get_statistics(
        self,
    ) -> list[ProbabilityBucket]:
        with self._lock:
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

    def get_summary(
        self,
    ) -> dict[str, float | int]:
        with self._lock:
            total = sum(
                bucket.total
                for bucket in self.buckets
            )

            wins = sum(
                bucket.wins
                for bucket in self.buckets
            )

        losses = max(
            0,
            total - wins,
        )

        winrate = (
            wins / total * 100.0
            if total
            else 0.0
        )

        return {
            "total": total,
            "wins": wins,
            "losses": losses,
            "winrate": winrate,
        }

    def clear(self) -> None:
        with self._lock:
            for bucket in self.buckets:
                bucket.total = 0
                bucket.wins = 0
                bucket.probability = 0.0


probability_calibrator = ProbabilityCalibrator()


__all__ = [
    "ProbabilityBucket",
    "ProbabilityCalibrator",
    "probability_calibrator",
]
