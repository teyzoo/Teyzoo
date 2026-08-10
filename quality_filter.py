from __future__ import annotations

import logging
from dataclasses import dataclass

from market import Candle
from models import Direction
from signal_engine import signal_engine


logger = logging.getLogger(
    "quality_filter"
)


# =========================================================
# DATA MODELS
# =========================================================


@dataclass(slots=True)
class TimeframeAnalysis:
    timeframe: str
    direction: Direction | None
    score: float
    reasons: list[str]


@dataclass(slots=True)
class QualityResult:
    accepted: bool
    direction: Direction | None
    quality_score: float
    confirmations: int
    total_checks: int
    reasons: list[str]
    rejected_reasons: list[str]
    timeframe_results: list[
        TimeframeAnalysis
    ]


# =========================================================
# TIMEFRAME ANALYSIS
# =========================================================


def analyze_timeframe(
    timeframe: str,
    candles: list[Candle],
) -> TimeframeAnalysis:
    if not candles:
        raise ValueError(
            f"No candles for timeframe {timeframe}."
        )

    if len(candles) < 20:
        raise ValueError(
            (
                f"Too few candles for "
                f"{timeframe}: {len(candles)}."
            )
        )

    result = signal_engine.analyze(
        candles
    )

    score = max(
        0.0,
        min(
            100.0,
            float(
                getattr(
                    result,
                    "score",
                    0.0,
                )
            ),
        ),
    )

    direction = getattr(
        result,
        "direction",
        None,
    )

    reasons = list(
        getattr(
            result,
            "reasons",
            [],
        )
        or []
    )

    logger.info(
        (
            "Timeframe %s | "
            "direction=%s | "
            "score=%.2f | "
            "reasons=%s"
        ),
        timeframe,
        direction,
        score,
        reasons,
    )

    return TimeframeAnalysis(
        timeframe=timeframe,
        direction=direction,
        score=score,
        reasons=reasons,
    )


# =========================================================
# QUALITY FILTER
# =========================================================


class QualityFilter:
    """
    Финальный фильтр качества.

    Основная идея:

        слабый TF
            ↓
        не подтверждает сигнал

        сильный TF
            ↓
        подтверждает направление

    Система учитывает:

    - направление;
    - score;
    - количество подтверждений;
    - процент согласия TF;
    - минимальный score;
    - конфликт направлений;
    - силу подтверждений;
    - бонус за полное согласие.

    Важно:

    quality_score НЕ является вероятностью WIN.
    """

    def __init__(
        self,
        minimum_quality: float = 65.0,
        minimum_confirmations: int = 2,
        minimum_timeframe_score: float = 55.0,
        full_agreement_bonus: float = 10.0,
        majority_bonus: float = 5.0,
        strong_score_bonus: float = 5.0,
    ) -> None:
        self.minimum_quality = max(
            0.0,
            min(
                100.0,
                float(
                    minimum_quality
                ),
            ),
        )

        self.minimum_confirmations = max(
            1,
            int(
                minimum_confirmations
            ),
        )

        self.minimum_timeframe_score = max(
            0.0,
            min(
                100.0,
                float(
                    minimum_timeframe_score
                ),
            ),
        )

        self.full_agreement_bonus = max(
            0.0,
            float(
                full_agreement_bonus
            ),
        )

        self.majority_bonus = max(
            0.0,
            float(
                majority_bonus
            ),
        )

        self.strong_score_bonus = max(
            0.0,
            float(
                strong_score_bonus
            ),
        )

    # =====================================================
    # CALCULATE QUALITY
    # =====================================================

    def _calculate_quality(
        self,
        selected: list[
            TimeframeAnalysis
        ],
        confirmations: int,
        total_valid: int,
    ) -> float:
        if not selected:
            return 0.0

        if total_valid <= 0:
            return 0.0

        # -------------------------------------------------
        # Average score
        # -------------------------------------------------

        average_score = (
            sum(
                item.score
                for item in selected
            )
            / len(selected)
        )

        average_score = max(
            0.0,
            min(
                100.0,
                average_score,
            ),
        )

        # -------------------------------------------------
        # Agreement
        # -------------------------------------------------

        agreement_ratio = (
            confirmations
            / total_valid
        )

        # -------------------------------------------------
        # Agreement bonus
        # -------------------------------------------------

        bonus = 0.0

        if confirmations == total_valid:
            bonus += (
                self.full_agreement_bonus
            )

        elif agreement_ratio >= 0.66:
            bonus += (
                self.majority_bonus
            )

        # -------------------------------------------------
        # Strong TF bonus
        # -------------------------------------------------

        strong_count = sum(
            item.score >= 80.0
            for item in selected
        )

        if strong_count >= 2:
            bonus += (
                self.strong_score_bonus
            )

        # -------------------------------------------------
        # Final
        # -------------------------------------------------

        quality = (
            average_score
            + bonus
        )

        return max(
            0.0,
            min(
                100.0,
                quality,
            ),
        )

    # =====================================================
    # EVALUATE
    # =====================================================

    def evaluate(
        self,
        analyses: list[
            TimeframeAnalysis
        ],
    ) -> QualityResult:
        logger.info(
            (
                "Quality evaluation started | "
                "TF=%s"
            ),
            len(analyses),
        )

        # =================================================
        # EMPTY
        # =================================================

        if not analyses:
            return QualityResult(
                accepted=False,
                direction=None,
                quality_score=0.0,
                confirmations=0,
                total_checks=0,
                reasons=[],
                rejected_reasons=[
                    "Нет данных для анализа."
                ],
                timeframe_results=[],
            )

        # =================================================
        # FILTER VALID
        # =================================================

        valid = [
            item
            for item in analyses
            if (
                item.direction is not None
                and item.score
                >= self.minimum_timeframe_score
            )
        ]

        low_quality = [
            item
            for item in analyses
            if (
                item.direction is not None
                and item.score
                < self.minimum_timeframe_score
            )
        ]

        for item in low_quality:
            logger.info(
                (
                    "Weak TF ignored | "
                    "%s | score=%.2f < %.2f"
                ),
                item.timeframe,
                item.score,
                self.minimum_timeframe_score,
            )

        # =================================================
        # NO VALID
        # =================================================

        if not valid:
            return QualityResult(
                accepted=False,
                direction=None,
                quality_score=0.0,
                confirmations=0,
                total_checks=len(
                    analyses
                ),
                reasons=[],
                rejected_reasons=[
                    (
                        "Нет достаточно сильных "
                        "таймфреймов."
                    )
                ],
                timeframe_results=analyses,
            )

        # =================================================
        # COUNT DIRECTIONS
        # =================================================

        up_count = sum(
            item.direction == Direction.UP
            for item in valid
        )

        down_count = sum(
            item.direction == Direction.DOWN
            for item in valid
        )

        logger.info(
            (
                "Direction counts | "
                "UP=%s | DOWN=%s | VALID=%s"
            ),
            up_count,
            down_count,
            len(valid),
        )

        # =================================================
        # CONFLICT
        # =================================================

        if up_count == down_count:
            return QualityResult(
                accepted=False,
                direction=None,
                quality_score=0.0,
                confirmations=0,
                total_checks=len(valid),
                reasons=[],
                rejected_reasons=[
                    (
                        "Таймфреймы разделились "
                        "по направлению."
                    )
                ],
                timeframe_results=analyses,
            )

        # =================================================
        # SELECT DIRECTION
        # =================================================

        if up_count > down_count:
            direction = Direction.UP
            confirmations = up_count
        else:
            direction = Direction.DOWN
            confirmations = down_count

        # =================================================
        # MATCHING TF
        # =================================================

        selected = [
            item
            for item in valid
            if item.direction == direction
        ]

        # =================================================
        # MINIMUM CONFIRMATIONS
        # =================================================

        rejected: list[str] = []

        if (
            confirmations
            < self.minimum_confirmations
        ):
            rejected.append(
                (
                    "Недостаточно подтверждений: "
                    f"{confirmations}/"
                    f"{self.minimum_confirmations}."
                )
            )

        # =================================================
        # AGREEMENT
        # =================================================

        agreement_ratio = (
            confirmations
            / len(valid)
        )

        if agreement_ratio < 0.60:
            rejected.append(
                (
                    "Слабое согласие таймфреймов: "
                    f"{agreement_ratio * 100:.1f}%."
                )
            )

        # =================================================
        # QUALITY
        # =================================================

        quality_score = (
            self._calculate_quality(
                selected=selected,
                confirmations=confirmations,
                total_valid=len(valid),
            )
        )

        # =================================================
        # REASONS
        # =================================================

        reasons: list[str] = []

        for item in selected:
            reasons.extend(
                item.reasons
            )

        reasons = list(
            dict.fromkeys(
                reasons
            )
        )

        reasons.append(
            (
                "Подтверждение TF: "
                f"{confirmations}/{len(valid)}"
            )
        )

        reasons.append(
            (
                "Согласованность TF: "
                f"{agreement_ratio * 100:.1f}%"
            )
        )

        average_score = (
            sum(
                item.score
                for item in selected
            )
            / len(selected)
        )

        reasons.append(
            (
                "Средний score подтверждений: "
                f"{average_score:.1f}%"
            )
        )

        reasons.append(
            (
                "Quality score: "
                f"{quality_score:.1f}%"
            )
        )

        # =================================================
        # MINIMUM QUALITY
        # =================================================

        if (
            quality_score
            < self.minimum_quality
        ):
            rejected.append(
                (
                    "Quality score ниже порога: "
                    f"{quality_score:.1f}% < "
                    f"{self.minimum_quality:.1f}%."
                )
            )

        # =================================================
        # ACCEPTED
        # =================================================

        accepted = not rejected

        if accepted:
            logger.info(
                (
                    "================================================ "
                    "QUALITY ACCEPTED | "
                    "direction=%s | "
                    "quality=%.2f | "
                    "confirmations=%s/%s"
                ),
                direction,
                quality_score,
                confirmations,
                len(valid),
            )
        else:
            logger.info(
                (
                    "QUALITY REJECTED | "
                    "direction=%s | "
                    "quality=%.2f | "
                    "reasons=%s"
                ),
                direction,
                quality_score,
                rejected,
            )

        # =================================================
        # RESULT
        # =================================================

        return QualityResult(
            accepted=accepted,
            direction=(
                direction
                if accepted
                else None
            ),
            quality_score=quality_score,
            confirmations=confirmations,
            total_checks=len(valid),
            reasons=reasons,
            rejected_reasons=rejected,
            timeframe_results=analyses,
        )


# =========================================================
# DEFAULT FILTER
# =========================================================


quality_filter = QualityFilter(
    minimum_quality=65.0,
    minimum_confirmations=2,
    minimum_timeframe_score=55.0,
    full_agreement_bonus=10.0,
    majority_bonus=5.0,
    strong_score_bonus=5.0,
)


# =========================================================
# EXPORTS
# =========================================================


__all__ = [
    "TimeframeAnalysis",
    "QualityResult",
    "QualityFilter",
    "analyze_timeframe",
    "quality_filter",
]
