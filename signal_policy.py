from __future__ import annotations

from dataclasses import dataclass

from probability import (
    ProbabilityCalibrator,
)


@dataclass(slots=True)
class SignalPolicyResult:
    allowed: bool

    reason: str

    quality_score: float

    historical_probability: (
        float | None
    )


class SignalPolicy:

    def __init__(
        self,
        calibrator: ProbabilityCalibrator,
        minimum_quality: float = 85.0,
        minimum_probability: float = 70.0,
    ):

        self.calibrator = calibrator

        self.minimum_quality = (
            minimum_quality
        )

        self.minimum_probability = (
            minimum_probability
        )

    def evaluate(
        self,
        quality_score: float,
    ) -> SignalPolicyResult:

        if (
            quality_score
            < self.minimum_quality
        ):

            return SignalPolicyResult(
                allowed=False,
                reason=(
                    "Quality score ниже "
                    "минимального порога."
                ),
                quality_score=quality_score,
                historical_probability=None,
            )

        probability = (
            self.calibrator.get_probability(
                quality_score
            )
        )

        # Пока недостаточно истории.
        if probability is None:

            return SignalPolicyResult(
                allowed=False,
                reason=(
                    "Недостаточно исторических "
                    "данных для подтверждения "
                    "вероятности."
                ),
                quality_score=quality_score,
                historical_probability=None,
            )

        if (
            probability
            < self.minimum_probability
        ):

            return SignalPolicyResult(
                allowed=False,
                reason=(
                    "Историческая вероятность "
                    "ниже установленного порога."
                ),
                quality_score=quality_score,
                historical_probability=probability,
            )

        return SignalPolicyResult(
            allowed=True,
            reason="Signal passed.",
            quality_score=quality_score,
            historical_probability=probability,
        )


signal_policy = SignalPolicy(
    calibrator=(
        __import__(
            "probability"
        ).probability_calibrator
    )
)
