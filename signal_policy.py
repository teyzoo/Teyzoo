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
    """
    Финальный фильтр допуска сигнала.

    Логика:

        Quality Score
             ↓
        Historical Probability
             ↓
          ALLOW / BLOCK

    При отсутствии истории сигнал можно пропустить,
    если SIGNAL_REQUIRE_HISTORICAL_PROBABILITY=false.
    """

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

        self.minimum_quality = max(
            0.0,
            min(
                100.0,
                float(minimum_quality),
            ),
        )

        self.minimum_probability = max(
            0.0,
            min(
                100.0,
                float(minimum_probability),
            ),
        )

        self.require_historical_probability = (
            bool(
                require_historical_probability
            )
        )

    def evaluate(
        self,
        quality_score: float,
    ) -> SignalPolicyResult:
        score = max(
            0.0,
            min(
                100.0,
                float(quality_score),
            ),
        )

        if score < self.minimum_quality:
            return SignalPolicyResult(
                allowed=False,
                reason=(
                    f"Quality Score {score:.1f}% "
                    f"ниже порога "
                    f"{self.minimum_quality:.1f}%."
                ),
                quality_score=score,
                historical_probability=None,
            )

        probability = (
            self.calibrator.get_probability(
                score
            )
        )

        if probability is None:
            if (
                self.require_historical_probability
            ):
                return SignalPolicyResult(
                    allowed=False,
                    reason=(
                        "Недостаточно исторических "
                        "данных для подтверждения "
                        "вероятности."
                    ),
                    quality_score=score,
                    historical_probability=None,
                )

            return SignalPolicyResult(
                allowed=True,
                reason=(
                    "Signal прошёл Quality Score. "
                    "Историческая вероятность "
                    "пока недоступна."
                ),
                quality_score=score,
                historical_probability=None,
            )

        if (
            probability
            < self.minimum_probability
        ):
            return SignalPolicyResult(
                allowed=False,
                reason=(
                    f"Историческая вероятность "
                    f"{probability:.1f}% ниже "
                    f"порога "
                    f"{self.minimum_probability:.1f}%."
                ),
                quality_score=score,
                historical_probability=probability,
            )

        return SignalPolicyResult(
            allowed=True,
            reason=(
                f"Signal passed: "
                f"quality={score:.1f}%, "
                f"historical="
                f"{probability:.1f}%."
            ),
            quality_score=score,
            historical_probability=probability,
        )


signal_policy = SignalPolicy(
    calibrator=probability_calibrator,
)


__all__ = [
    "SignalPolicyResult",
    "SignalPolicy",
    "signal_policy",
]
