from __future__ import annotations

from dataclasses import dataclass

from config import (
    SIGNAL_MINIMUM_PROBABILITY,
    SIGNAL_MINIMUM_QUALITY,
    SIGNAL_REQUIRE_HISTORICAL_PROBABILITY,
)

from probability import (
    ProbabilityCalibrator,
    probability_calibrator,
)


@dataclass(slots=True)
class SignalPolicyResult:
    allowed: bool
    reason: str

    quality_score: float
    historical_probability: float | None


class SignalPolicy:

    def __init__(
        self,
        calibrator: ProbabilityCalibrator,
        minimum_quality: float = SIGNAL_MINIMUM_QUALITY,
        minimum_probability: float = SIGNAL_MINIMUM_PROBABILITY,
        require_historical_probability: bool = (
            SIGNAL_REQUIRE_HISTORICAL_PROBABILITY
        ),
    ) -> None:
        self.calibrator = calibrator

        self.minimum_quality = float(
            minimum_quality
        )

        self.minimum_probability = float(
            minimum_probability
        )

        self.require_historical_probability = bool(
            require_historical_probability
        )

    def evaluate(
        self,
        quality_score: float,
    ) -> SignalPolicyResult:
        quality_score = max(
            0.0,
            min(
                100.0,
                float(quality_score),
            ),
        )

        if quality_score < self.minimum_quality:
            return SignalPolicyResult(
                allowed=False,
                reason=(
                    "Quality Score ниже "
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

        if probability is None:
            if self.require_historical_probability:
                return SignalPolicyResult(
                    allowed=False,
                    reason=(
                        "Недостаточно исторических "
                        "данных для подтверждения."
                    ),
                    quality_score=quality_score,
                    historical_probability=None,
                )

            return SignalPolicyResult(
                allowed=True,
                reason=(
                    "Quality Score прошёл. "
                    "Исторической статистики пока "
                    "недостаточно."
                ),
                quality_score=quality_score,
                historical_probability=None,
            )

        if probability < self.minimum_probability:
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
    calibrator=probability_calibrator
)


__all__ = [
    "SignalPolicyResult",
    "SignalPolicy",
    "signal_policy",
]
