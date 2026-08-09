from __future__ import annotations

import logging
from dataclasses import dataclass

from probability import (
    ProbabilityCalibrator,
    probability_calibrator,
)


logger = logging.getLogger(
    "signal_policy"
)


@dataclass(slots=True)
class SignalPolicyResult:

    allowed: bool

    reason: str

    quality_score: float

    historical_probability: float | None

    bucket_total: int

    bucket_wins: int

    bucket_losses: int


class SignalPolicy:

    """
    Финальный фильтр перед отправкой сигнала.

    Сигнал допускается только если:

    1. Quality Score >= minimum_quality
    2. Для этого диапазона score есть достаточно
       исторических результатов.
    3. Историческая вероятность >= minimum_probability.

    Quality Score НЕ является вероятностью выигрыша.
    """

    def __init__(
        self,
        calibrator: ProbabilityCalibrator,
        minimum_quality: float = 85.0,
        minimum_probability: float = 70.0,
        minimum_history: int = 100,
    ):

        self.calibrator = calibrator

        self.minimum_quality = (
            minimum_quality
        )

        self.minimum_probability = (
            minimum_probability
        )

        self.minimum_history = (
            minimum_history
        )

    async def refresh(self):

        await self.calibrator.refresh()

    def evaluate(
        self,
        quality_score: float,
    ) -> SignalPolicyResult:

        quality_score = float(
            quality_score
        )

        # ====================================================
        # QUALITY
        # ====================================================

        if (
            quality_score
            < self.minimum_quality
        ):

            return SignalPolicyResult(
                allowed=False,
                reason=(
                    "Quality Score ниже "
                    f"{self.minimum_quality:.1f}%."
                ),
                quality_score=quality_score,
                historical_probability=None,
                bucket_total=0,
                bucket_wins=0,
                bucket_losses=0,
            )

        # ====================================================
        # BUCKET
        # ====================================================

        bucket = (
            self.calibrator.get_bucket(
                quality_score
            )
        )

        if bucket is None:

            return SignalPolicyResult(
                allowed=False,
                reason=(
                    "Quality Score не "
                    "попадает в допустимый "
                    "диапазон."
                ),
                quality_score=quality_score,
                historical_probability=None,
                bucket_total=0,
                bucket_wins=0,
                bucket_losses=0,
            )

        # ====================================================
        # HISTORY
        # ====================================================

        if (
            bucket.total
            < self.minimum_history
        ):

            return SignalPolicyResult(
                allowed=False,
                reason=(
                    "Недостаточно исторических "
                    "результатов для этого "
                    "диапазона Quality Score."
                ),
                quality_score=quality_score,
                historical_probability=None,
                bucket_total=bucket.total,
                bucket_wins=bucket.wins,
                bucket_losses=bucket.losses,
            )

        # ====================================================
        # PROBABILITY
        # ====================================================

        probability = (
            self.calibrator.get_probability(
                quality_score
            )
        )

        if probability is None:

            return SignalPolicyResult(
                allowed=False,
                reason=(
                    "Историческая вероятность "
                    "не рассчитана."
                ),
                quality_score=quality_score,
                historical_probability=None,
                bucket_total=bucket.total,
                bucket_wins=bucket.wins,
                bucket_losses=bucket.losses,
            )

        # ====================================================
        # PROBABILITY FILTER
        # ====================================================

        if (
            probability
            < self.minimum_probability
        ):

            return SignalPolicyResult(
                allowed=False,
                reason=(
                    "Историческая вероятность "
                    f"{probability:.1f}% ниже "
                    f"минимального порога "
                    f"{self.minimum_probability:.1f}%."
                ),
                quality_score=quality_score,
                historical_probability=probability,
                bucket_total=bucket.total,
                bucket_wins=bucket.wins,
                bucket_losses=bucket.losses,
            )

        # ====================================================
        # ACCEPT
        # ====================================================

        logger.info(
            "Signal passed policy: "
            "score=%.2f probability=%.2f "
            "history=%s",
            quality_score,
            probability,
            bucket.total,
        )

        return SignalPolicyResult(
            allowed=True,
            reason="Signal passed all filters.",
            quality_score=quality_score,
            historical_probability=probability,
            bucket_total=bucket.total,
            bucket_wins=bucket.wins,
            bucket_losses=bucket.losses,
        )


signal_policy = SignalPolicy(
    calibrator=probability_calibrator,
    minimum_quality=85.0,
    minimum_probability=70.0,
    minimum_history=100,
)
