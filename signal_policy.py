from __future__ import annotations

from dataclasses import dataclass

from probability import (
    ProbabilityCalibrator,
    ProbabilityResult,
    probability_calibrator,
)


# ============================================================
# НАСТРОЙКИ
# ============================================================

DEFAULT_MINIMUM_QUALITY = 85.0

DEFAULT_MINIMUM_PROBABILITY = 70.0

# Минимальное количество исторических сделок,
# необходимое для разрешения сигнала.
DEFAULT_MINIMUM_SAMPLES = 100


# ============================================================
# RESULT
# ============================================================

@dataclass(slots=True)
class SignalPolicyResult:

    allowed: bool

    reason: str

    quality_score: float

    historical_probability: float | None

    historical_samples: int

    historical_wins: int

    historical_losses: int

    reliable_history: bool


# ============================================================
# POLICY
# ============================================================

class SignalPolicy:

    def __init__(
        self,
        calibrator: ProbabilityCalibrator,
        minimum_quality: float = (
            DEFAULT_MINIMUM_QUALITY
        ),
        minimum_probability: float = (
            DEFAULT_MINIMUM_PROBABILITY
        ),
        minimum_samples: int = (
            DEFAULT_MINIMUM_SAMPLES
        ),
    ):

        self.calibrator = calibrator

        self.minimum_quality = (
            minimum_quality
        )

        self.minimum_probability = (
            minimum_probability
        )

        self.minimum_samples = (
            minimum_samples
        )

    # ========================================================
    # EVALUATE
    # ========================================================

    def evaluate(
        self,
        quality_score: float,
    ) -> SignalPolicyResult:

        # ----------------------------------------------------
        # Защита от неправильного score
        # ----------------------------------------------------

        quality_score = max(
            0.0,
            min(
                100.0,
                float(quality_score),
            ),
        )

        # ----------------------------------------------------
        # QUALITY
        # ----------------------------------------------------

        if (
            quality_score
            < self.minimum_quality
        ):

            return self._reject(
                reason=(
                    "Quality score "
                    f"{quality_score:.1f}% "
                    "ниже минимального "
                    f"порога "
                    f"{self.minimum_quality:.1f}%."
                ),
                quality_score=quality_score,
            )

        # ----------------------------------------------------
        # Получаем историческую статистику
        # ----------------------------------------------------

        result = (
            self.calibrator.get_result(
                quality_score
            )
        )

        # ----------------------------------------------------
        # Нет истории
        # ----------------------------------------------------

        if result.total_samples <= 0:

            return self._reject(
                reason=(
                    "Нет исторических "
                    "данных для этого "
                    "диапазона Quality Score."
                ),
                quality_score=quality_score,
            )

        # ----------------------------------------------------
        # Недостаточная выборка
        # ----------------------------------------------------

        if (
            result.total_samples
            < self.minimum_samples
        ):

            return SignalPolicyResult(
                allowed=False,
                reason=(
                    "Недостаточно исторических "
                    "наблюдений: "
                    f"{result.total_samples}/"
                    f"{self.minimum_samples}."
                ),
                quality_score=quality_score,
                historical_probability=(
                    None
                ),
                historical_samples=(
                    result.total_samples
                ),
                historical_wins=(
                    result.wins
                ),
                historical_losses=(
                    result.losses
                ),
                reliable_history=False,
            )

        # ----------------------------------------------------
        # История должна быть reliable
        # ----------------------------------------------------

        if not result.reliable:

            return SignalPolicyResult(
                allowed=False,
                reason=(
                    "Историческая статистика "
                    "ещё недостаточно надёжна."
                ),
                quality_score=quality_score,
                historical_probability=(
                    result.probability
                ),
                historical_samples=(
                    result.total_samples
                ),
                historical_wins=(
                    result.wins
                ),
                historical_losses=(
                    result.losses
                ),
                reliable_history=False,
            )

        probability = (
            result.probability
        )

        # ----------------------------------------------------
        # Probability отсутствует
        # ----------------------------------------------------

        if probability is None:

            return SignalPolicyResult(
                allowed=False,
                reason=(
                    "Не удалось получить "
                    "историческую вероятность."
                ),
                quality_score=quality_score,
                historical_probability=None,
                historical_samples=(
                    result.total_samples
                ),
                historical_wins=(
                    result.wins
                ),
                historical_losses=(
                    result.losses
                ),
                reliable_history=False,
            )

        # ----------------------------------------------------
        # Проверяем вероятность
        # ----------------------------------------------------

        if (
            probability
            < self.minimum_probability
        ):

            return SignalPolicyResult(
                allowed=False,
                reason=(
                    "Историческая вероятность "
                    f"{probability:.1f}% "
                    "ниже минимального "
                    f"порога "
                    f"{self.minimum_probability:.1f}%."
                ),
                quality_score=quality_score,
                historical_probability=(
                    probability
                ),
                historical_samples=(
                    result.total_samples
                ),
                historical_wins=(
                    result.wins
                ),
                historical_losses=(
                    result.losses
                ),
                reliable_history=True,
            )

        # ----------------------------------------------------
        # Сигнал разрешён
        # ----------------------------------------------------

        return SignalPolicyResult(
            allowed=True,
            reason=(
                "Signal passed all policy checks."
            ),
            quality_score=quality_score,
            historical_probability=(
                probability
            ),
            historical_samples=(
                result.total_samples
            ),
            historical_wins=(
                result.wins
            ),
            historical_losses=(
                result.losses
            ),
            reliable_history=True,
        )

    # ========================================================
    # REJECT HELPER
    # ========================================================

    @staticmethod
    def _reject(
        reason: str,
        quality_score: float,
    ) -> SignalPolicyResult:

        return SignalPolicyResult(
            allowed=False,
            reason=reason,
            quality_score=quality_score,
            historical_probability=None,
            historical_samples=0,
            historical_wins=0,
            historical_losses=0,
            reliable_history=False,
        )

    # ========================================================
    # EXPLAIN
    # ========================================================

    def explain(
        self,
        quality_score: float,
    ) -> str:

        result = self.evaluate(
            quality_score
        )

        if result.allowed:

            probability_text = (
                "неизвестно"
                if (
                    result.historical_probability
                    is None
                )
                else (
                    f"{result.historical_probability:.1f}%"
                )
            )

            return (
                "✅ SIGNAL ALLOWED\n"
                f"Quality: "
                f"{result.quality_score:.1f}%\n"
                f"Historical probability: "
                f"{probability_text}\n"
                f"Samples: "
                f"{result.historical_samples}\n"
                f"Wins: "
                f"{result.historical_wins}\n"
                f"Losses: "
                f"{result.historical_losses}"
            )

        return (
            "⛔ SIGNAL REJECTED\n"
            f"Quality: "
            f"{result.quality_score:.1f}%\n"
            f"Reason: "
            f"{result.reason}\n"
            f"Samples: "
            f"{result.historical_samples}"
        )


# ============================================================
# SINGLETON
# ============================================================

signal_policy = SignalPolicy(
    calibrator=probability_calibrator,

    minimum_quality=85.0,

    minimum_probability=70.0,

    minimum_samples=100,
)
