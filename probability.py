from __future__ import annotations
import logging
from dataclasses import dataclass
from database import (
    get_completed_signals,
)
logger = logging.getLogger(
    "probability"
)
# ============================================================
# BUCKET
# ============================================================
@dataclass(slots=True)
class ProbabilityBucket:
    minimum_score: float
    maximum_score: float
    total: int = 0
    wins: int = 0
    losses: int = 0
    probability: float = 0.0
# ============================================================
# CALIBRATOR
# ============================================================
class ProbabilityCalibrator:
    """
    Исторический калибратор сигналов.
    ВАЖНО:
    Мы НЕ считаем Quality Score настоящей
    вероятностью выигрыша.
    Например:
        Quality Score = 90%
    НЕ означает:
        вероятность выигрыша = 90%.
    Здесь вероятность рассчитывается
    исключительно по завершённым сделкам
    из базы данных.
    Например:
        87 побед
        13 поражений
    =
        87 / 100 * 100
        = 87%
    """
    def __init__(
        self,
        minimum_history: int = 100,
    ):
        self.minimum_history = (
            minimum_history
        )
        self.buckets = [
            ProbabilityBucket(
                minimum_score=50.0,
                maximum_score=60.0,
            ),
            ProbabilityBucket(
                minimum_score=60.0,
                maximum_score=70.0,
            ),
            ProbabilityBucket(
                minimum_score=70.0,
                maximum_score=80.0,
            ),
            ProbabilityBucket(
                minimum_score=80.0,
                maximum_score=90.0,
            ),
            ProbabilityBucket(
                minimum_score=90.0,
                maximum_score=101.0,
            ),
        ]
    # ========================================================
    # FIND BUCKET
    # ========================================================
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
    # ========================================================
    # RESET
    # ========================================================
    def reset(self):
        for bucket in self.buckets:
            bucket.total = 0
            bucket.wins = 0
            bucket.losses = 0
            bucket.probability = 0.0
    # ========================================================
    # ADD RESULT
    # ========================================================
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
        else:
            bucket.losses += 1
        bucket.probability = (
            bucket.wins
            / bucket.total
            * 100
        )
    # ========================================================
    # LOAD DATABASE HISTORY
    # ========================================================
    async def refresh(
        self,
        limit: int = 10000,
    ):
        logger.info(
            "Refreshing probability "
            "calibration from database..."
        )
        self.reset()
        try:
            signals = (
                await get_completed_signals(
                    limit=limit
                )
            )
        except Exception:
            logger.exception(
                "Could not load completed "
                "signals."
            )
            return
        for signal in signals:
            if signal.score is None:
                continue
            if signal.status == "WIN":
                self.add_result(
                    score=float(
                        signal.score
                    ),
                    won=True,
                )
            elif signal.status == "LOSS":
                self.add_result(
                    score=float(
                        signal.score
                    ),
                    won=False,
                )
        logger.info(
            "Probability calibration "
            "refreshed. Signals: %s",
            len(signals),
        )
        for bucket in self.buckets:
            logger.info(
                "Bucket %.0f-%.0f: "
                "total=%s wins=%s losses=%s "
                "probability=%.2f%%",
                bucket.minimum_score,
                bucket.maximum_score,
                bucket.total,
                bucket.wins,
                bucket.losses,
                bucket.probability,
            )
    # ========================================================
    # PROBABILITY
    # ========================================================
    def get_probability(
        self,
        score: float,
    ) -> float | None:
        bucket = self._find_bucket(
            score
        )
        if bucket is None:
            return None
        #
        # Пока истории мало —
        # НЕ выдаём пользователю
        # выдуманную вероятность.
        #
        if (
            bucket.total
            < self.minimum_history
        ):
            return None
        return bucket.probability
    # ========================================================
    # BUCKET INFORMATION
    # ========================================================
    def get_bucket(
        self,
        score: float,
    ) -> ProbabilityBucket | None:
        return self._find_bucket(
            score
        )
    # ========================================================
    # STATISTICS
    # ========================================================
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
                    "losses": (
                        bucket.losses
                    ),
                    "probability": (
                        bucket.probability
                    ),
                    "enough_history": (
                        bucket.total
                        >= self.minimum_history
                    ),
                }
            )
        return result
# ============================================================
# GLOBAL CALIBRATOR
# ============================================================
probability_calibrator = (
    ProbabilityCalibrator(
        minimum_history=100
    )
)
# ============================================================
# INITIALIZATION
# ============================================================
async def initialize_probability():
    """
    Загружает исторические результаты
    из PostgreSQL при запуске приложения.
    """
    await probability_calibrator.refresh()
# ============================================================
# REFRESH
# ============================================================
async def refresh_probability():
    """
    Повторно загружает статистику.
    Вызывается после появления новых
    завершённых сигналов.
    """
    await probability_calibrator.refresh()
