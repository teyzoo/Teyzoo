from __future__ import annotations
import logging
from dataclasses import dataclass
from market import Candle
from models import Direction
from signal_engine import signal_engine
logger = logging.getLogger("quality_filter")
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
    timeframe_results: list[TimeframeAnalysis]
# =========================================================
# TIMEFRAME WEIGHTS
# =========================================================
# Старшие TF имеют больший вес.
#
# 1m  -> 20%
# 5m  -> 35%
# 15m -> 45%
#
# Если используется другой TF, ему будет назначен
# нейтральный вес.
TIMEFRAME_WEIGHTS: dict[str, float] = {
    "1m": 0.20,
    "3m": 0.25,
    "5m": 0.35,
    "15m": 0.45,
    "30m": 0.50,
    "1h": 0.60,
    "4h": 0.70,
}
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
    result = signal_engine.analyze(candles)
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
    Финальный фильтр качества торгового сигнала.
    ВАЖНО:
    quality_score НЕ является вероятностью WIN.
    Он показывает насколько хорошо текущий набор
    технических подтверждений соответствует правилам
    фильтра.
    Основные факторы:
        1. сила score каждого TF;
        2. согласованность направлений;
        3. количество подтверждений;
        4. вес старших таймфреймов;
        5. бонус за полное совпадение;
        6. штраф за конфликт;
        7. бонус за сильные TF.
    """
    def __init__(
        self,
        minimum_quality: float = 85.0,
        minimum_confirmations: int = 2,
        minimum_timeframe_score: float = 55.0,
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
    # =====================================================
    # TF WEIGHT
    # =====================================================
    @staticmethod
    def _timeframe_weight(
        timeframe: str,
    ) -> float:
        timeframe = (
            str(timeframe)
            .strip()
            .lower()
        )
        return TIMEFRAME_WEIGHTS.get(
            timeframe,
            0.30,
        )
    # =====================================================
    # WEIGHTED SCORE
    # =====================================================
    def _weighted_score(
        self,
        selected: list[TimeframeAnalysis],
    ) -> float:
        if not selected:
            return 0.0
        weighted_sum = 0.0
        total_weight = 0.0
        for item in selected:
            weight = (
                self._timeframe_weight(
                    item.timeframe
                )
            )
            weighted_sum += (
                item.score
                * weight
            )
            total_weight += weight
        if total_weight <= 0:
            return 0.0
        return (
            weighted_sum
            / total_weight
        )
    # =====================================================
    # STRONG TF BONUS
    # =====================================================
    @staticmethod
    def _strong_tf_bonus(
        selected: list[TimeframeAnalysis],
    ) -> float:
        if not selected:
            return 0.0
        strong_80 = sum(
            item.score >= 80.0
            for item in selected
        )
        strong_70 = sum(
            item.score >= 70.0
            for item in selected
        )
        bonus = 0.0
        if strong_80 >= 3:
            bonus += 12.0
        elif strong_80 >= 2:
            bonus += 8.0
        elif strong_80 >= 1:
            bonus += 4.0
        elif strong_70 >= 2:
            bonus += 3.0
        return bonus
    # =====================================================
    # AGREEMENT BONUS
    # =====================================================
    @staticmethod
    def _agreement_bonus(
        confirmations: int,
        total_valid: int,
    ) -> float:
        if total_valid <= 0:
            return 0.0
        ratio = (
            confirmations
            / total_valid
        )
        if ratio >= 1.0:
            return 15.0
        if ratio >= 0.80:
            return 9.0
        if ratio >= 0.66:
            return 5.0
        if ratio >= 0.60:
            return 2.0
        return 0.0
    # =====================================================
    # CONFLICT PENALTY
    # =====================================================
    @staticmethod
    def _conflict_penalty(
        selected: list[TimeframeAnalysis],
        valid: list[TimeframeAnalysis],
    ) -> float:
        if not valid:
            return 0.0
        conflicting = [
            item
            for item in valid
            if item not in selected
        ]
        if not conflicting:
            return 0.0
        total_conflict_score = sum(
            item.score
            for item in conflicting
        )
        return min(
            15.0,
            total_conflict_score
            / len(conflicting)
            * 0.15,
        )
    # =====================================================
    # CALCULATE QUALITY
    # =====================================================
    def _calculate_quality(
        self,
        selected: list[TimeframeAnalysis],
        valid: list[TimeframeAnalysis],
        confirmations: int,
    ) -> float:
        if not selected:
            return 0.0
        if not valid:
            return 0.0
        # -------------------------------------------------
        # BASE
        # -------------------------------------------------
        weighted_score = (
            self._weighted_score(
                selected
            )
        )
        # -------------------------------------------------
        # AGREEMENT
        # -------------------------------------------------
        agreement_bonus = (
            self._agreement_bonus(
                confirmations=confirmations,
                total_valid=len(valid),
            )
        )
        # -------------------------------------------------
        # STRONG TF
        # -------------------------------------------------
        strong_bonus = (
            self._strong_tf_bonus(
                selected
            )
        )
        # -------------------------------------------------
        # CONFLICT
        # -------------------------------------------------
        conflict_penalty = (
            self._conflict_penalty(
                selected=selected,
                valid=valid,
            )
        )
        # -------------------------------------------------
        # TIMEFRAME COUNT BONUS
        # -------------------------------------------------
        confirmation_bonus = 0.0
        if confirmations >= 3:
            confirmation_bonus = 8.0
        elif confirmations >= 2:
            confirmation_bonus = 3.0
        # -------------------------------------------------
        # FINAL
        # -------------------------------------------------
        quality = (
            weighted_score
            + agreement_bonus
            + strong_bonus
            + confirmation_bonus
            - conflict_penalty
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
        analyses: list[TimeframeAnalysis],
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
        # VALID
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
                total_checks=len(analyses),
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
        # DIRECTION COUNTS
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
                "UP=%s | "
                "DOWN=%s | "
                "VALID=%s"
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
        # SELECTED
        # =================================================
        selected = [
            item
            for item in valid
            if item.direction == direction
        ]
        # =================================================
        # REJECTED REASONS
        # =================================================
        rejected: list[str] = []
        # -------------------------------------------------
        # MINIMUM CONFIRMATIONS
        # -------------------------------------------------
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
        # -------------------------------------------------
        # AGREEMENT
        # -------------------------------------------------
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
                valid=valid,
                confirmations=confirmations,
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
        weighted_score = (
            self._weighted_score(
                selected
            )
        )
        reasons.append(
            (
                "Взвешенный score TF: "
                f"{weighted_score:.1f}%"
            )
        )
        strong_bonus = (
            self._strong_tf_bonus(
                selected
            )
        )
        if strong_bonus > 0:
            reasons.append(
                (
                    "Бонус сильных TF: "
                    f"+{strong_bonus:.1f}"
                )
            )
        agreement_bonus = (
            self._agreement_bonus(
                confirmations=confirmations,
                total_valid=len(valid),
            )
        )
        if agreement_bonus > 0:
            reasons.append(
                (
                    "Бонус согласованности: "
                    f"+{agreement_bonus:.1f}"
                )
            )
        conflict_penalty = (
            self._conflict_penalty(
                selected=selected,
                valid=valid,
            )
        )
        if conflict_penalty > 0:
            reasons.append(
                (
                    "Штраф конфликта: "
                    f"-{conflict_penalty:.1f}"
                )
            )
        reasons.append(
            (
                "Итоговый Quality score: "
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
                    "================================================"
                    " QUALITY ACCEPTED | "
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
    minimum_quality=85.0,
    minimum_confirmations=2,
    minimum_timeframe_score=55.0,
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
