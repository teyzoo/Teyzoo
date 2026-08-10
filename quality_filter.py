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
    timeframe_results: list[TimeframeAnalysis]
# =========================================================
# TIMEFRAME ANALYSIS
# =========================================================
def analyze_timeframe(
    timeframe: str,
    candles: list[Candle],
) -> TimeframeAnalysis:
    result = signal_engine.analyze(
        candles
    )
    logger.info(
        (
            "Timeframe %s | "
            "direction=%s | "
            "score=%.2f | "
            "confirmations=%s/%s | "
            "reasons=%s"
        ),
        timeframe,
        result.direction,
        result.score,
        result.confirmations,
        result.total_checks,
        result.reasons,
    )
    return TimeframeAnalysis(
        timeframe=timeframe,
        direction=result.direction,
        score=result.score,
        reasons=list(
            result.reasons
        ),
    )
# =========================================================
# QUALITY FILTER
# =========================================================
class QualityFilter:
    """
    Финальный фильтр торгового сигнала.
    Логика:
        1. Анализируем все TF.
        2. Убираем TF без направления.
        3. Считаем UP / DOWN.
        4. Выбираем большинство.
        5. Проверяем минимум подтверждений.
        6. Считаем средний score выбранного
           направления.
        7. Добавляем небольшой бонус
           за согласованность TF.
        8. Проверяем минимальное качество.
    Важно:
    Quality Score НЕ заменяет score SignalEngine.
    SignalEngine показывает силу сигналов
    внутри конкретного TF.
    QualityFilter показывает качество
    комбинации нескольких TF.
    """
    def __init__(
        self,
        minimum_quality: float = 60.0,
        minimum_confirmations: int = 2,
        full_agreement_bonus: float = 10.0,
        majority_bonus: float = 5.0,
    ) -> None:
        self.minimum_quality = float(
            minimum_quality
        )
        self.minimum_confirmations = max(
            1,
            int(
                minimum_confirmations
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
    # =====================================================
    # QUALITY SCORE
    # =====================================================
    def _calculate_quality(
        self,
        average_score: float,
        confirmations: int,
        total_valid: int,
    ) -> float:
        if total_valid <= 0:
            return 0.0
        average_score = max(
            0.0,
            min(
                100.0,
                float(
                    average_score
                ),
            ),
        )
        agreement_ratio = (
            confirmations
            / total_valid
        )
        # =================================================
        # FULL AGREEMENT
        # =================================================
        if confirmations == total_valid:
            bonus = (
                self.full_agreement_bonus
            )
        # =================================================
        # MAJORITY
        # =================================================
        elif agreement_ratio >= 0.66:
            bonus = (
                self.majority_bonus
            )
        # =================================================
        # WEAK MAJORITY
        # =================================================
        else:
            bonus = 0.0
        quality_score = (
            average_score
            + bonus
        )
        return min(
            100.0,
            quality_score,
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
        rejected: list[str] = []
        logger.info(
            (
                "Quality evaluation started. "
                "Timeframes=%s"
            ),
            len(analyses),
        )
        # =================================================
        # EMPTY
        # =================================================
        if not analyses:
            logger.info(
                "Quality rejected: "
                "no timeframe analyses."
            )
            return QualityResult(
                accepted=False,
                direction=None,
                quality_score=0.0,
                confirmations=0,
                total_checks=0,
                reasons=[],
                rejected_reasons=[
                    "Нет данных для анализа таймфреймов."
                ],
                timeframe_results=[],
            )
        # =================================================
        # VALID
        # =================================================
        valid = [
            item
            for item in analyses
            if item.direction is not None
        ]
        if not valid:
            logger.info(
                "Quality rejected: "
                "no confirmed timeframes."
            )
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
                    "Нет подтверждённых таймфреймов."
                ],
                timeframe_results=analyses,
            )
        # =================================================
        # COUNT
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
                "Direction confirmation: "
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
            logger.info(
                "Quality rejected: "
                "no unified direction."
            )
            return QualityResult(
                accepted=False,
                direction=None,
                quality_score=0.0,
                confirmations=0,
                total_checks=len(
                    valid
                ),
                reasons=[],
                rejected_reasons=[
                    "Нет единого направления."
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
        logger.info(
            (
                "Selected direction: %s | "
                "confirmations=%s"
            ),
            direction,
            confirmations,
        )
        # =================================================
        # MINIMUM CONFIRMATIONS
        # =================================================
        if confirmations < (
            self.minimum_confirmations
        ):
            rejected.append(
                (
                    "Недостаточно подтверждений "
                    "по таймфреймам."
                )
            )
            logger.info(
                (
                    "Rejected: confirmations=%s "
                    "< minimum=%s"
                ),
                confirmations,
                self.minimum_confirmations,
            )
        # =================================================
        # SELECT MATCHING
        # =================================================
        selected = [
            item
            for item in valid
            if item.direction == direction
        ]
        if not selected:
            return QualityResult(
                accepted=False,
                direction=None,
                quality_score=0.0,
                confirmations=confirmations,
                total_checks=len(
                    valid
                ),
                reasons=[],
                rejected_reasons=[
                    (
                        "Не удалось выбрать "
                        "подтверждающие таймфреймы."
                    )
                ],
                timeframe_results=analyses,
            )
        # =================================================
        # AVERAGE SCORE
        # =================================================
        average_score = (
            sum(
                item.score
                for item in selected
            )
            / len(selected)
        )
        # =================================================
        # AGREEMENT
        # =================================================
        agreement_ratio = (
            confirmations
            / len(valid)
        )
        # =================================================
        # BONUS
        # =================================================
        if confirmations == len(valid):
            agreement_bonus = (
                self.full_agreement_bonus
            )
        elif agreement_ratio >= 0.66:
            agreement_bonus = (
                self.majority_bonus
            )
        else:
            agreement_bonus = 0.0
        # =================================================
        # QUALITY
        # =================================================
        quality_score = (
            self._calculate_quality(
                average_score=average_score,
                confirmations=confirmations,
                total_valid=len(valid),
            )
        )
        logger.info(
            (
                "Quality calculation: "
                "average=%.2f | "
                "agreement=%.2f%% | "
                "bonus=%.2f | "
                "final=%.2f | "
                "minimum=%.2f"
            ),
            average_score,
            agreement_ratio * 100.0,
            agreement_bonus,
            quality_score,
            self.minimum_quality,
        )
        # =================================================
        # MINIMUM QUALITY
        # =================================================
        if quality_score < (
            self.minimum_quality
        ):
            rejected.append(
                (
                    "Качество ниже минимального "
                    f"порога "
                    f"{self.minimum_quality:.1f}%."
                )
            )
            logger.info(
                (
                    "Rejected: quality %.2f "
                    "< minimum %.2f"
                ),
                quality_score,
                self.minimum_quality,
            )
        # =================================================
        # REASONS
        # =================================================
        reasons: list[str] = []
        for item in selected:
            reasons.extend(
                item.reasons
            )
        # Удаляем дубликаты,
        # сохраняя порядок.
        reasons = list(
            dict.fromkeys(
                reasons
            )
        )
        # =================================================
        # QUALITY REASON
        # =================================================
        reasons.append(
            (
                "Подтверждение TF: "
                f"{confirmations}/{len(valid)}"
            )
        )
        reasons.append(
            (
                "Средний score TF: "
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
        # ACCEPTED
        # =================================================
        accepted = not rejected
        if accepted:
            logger.info(
                (
                    "QUALITY ACCEPTED | "
                    "direction=%s | "
                    "score=%.2f | "
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
                    "score=%.2f | "
                    "reasons=%s"
                ),
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
    minimum_quality=60.0,
    minimum_confirmations=2,
    full_agreement_bonus=10.0,
    majority_bonus=5.0,
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
