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
    """
    Анализирует один таймфрейм через signal_engine.
    Важно:
    - не изменяет candles;
    - полностью сохраняет score signal_engine;
    - сохраняет исходные reasons;
    - direction=None считается конфликтующим
      / неподтверждённым таймфреймом.
    """
    result = signal_engine.analyze(
        candles
    )
    logger.info(
        (
            "Timeframe %s | "
            "direction=%s | "
            "score=%.2f | "
            "reasons=%s"
        ),
        timeframe,
        result.direction,
        result.score,
        result.reasons,
    )
    return TimeframeAnalysis(
        timeframe=timeframe,
        direction=result.direction,
        score=result.score,
        reasons=list(result.reasons),
    )
# =========================================================
# QUALITY FILTER
# =========================================================
class QualityFilter:
    """
    Фильтр качества торгового сигнала.
    Основная задача:
    1. Проверить таймфреймы.
    2. Найти единое направление.
    3. Посчитать количество подтверждений.
    4. Рассчитать итоговое качество.
    5. Отбросить слабые/конфликтующие сигналы.
    =====================================================
    НОВАЯ МОДЕЛЬ QUALITY SCORE
    =====================================================
    Старый вариант:
        average_score + agreement_bonus
    приводил к ситуации:
        50 + 10 = 60
    даже когда два таймфрейма полностью
    подтверждали одно направление.
    Теперь итоговая оценка учитывает:
        1. качество самих подтверждающих TF;
        2. долю согласных TF;
        3. количество подтверждений;
        4. наличие полного согласования.
    Это позволяет нормальным согласованным
    сигналам проходить фильтр, но не пропускает
    одиночный слабый сигнал.
    """
    def __init__(
        self,
        minimum_quality: float = 70.0,
        minimum_confirmations: int = 2,
    ) -> None:
        self.minimum_quality = float(
            minimum_quality
        )
        self.minimum_confirmations = max(
            1,
            int(minimum_confirmations),
        )
    # =====================================================
    # QUALITY SCORE
    # =====================================================
    @staticmethod
    def _calculate_quality(
        average_score: float,
        confirmations: int,
        total_valid: int,
    ) -> float:
        """
        Рассчитывает итоговое качество.
        Базой является средний score подтверждающих
        таймфреймов.
        Затем добавляется бонус за согласованность.
        Максимальный bonus = 30%.
        Примеры:
            2/3 подтверждения:
                bonus = 20
            3/3 подтверждения:
                bonus = 30
        Таким образом:
            50 + 20 = 70
            50 + 30 = 80
        Более сильный signal_engine score:
            70 + 20 = 90
        Это значительно логичнее старой схемы,
        где максимальный bonus составлял всего 10%.
        """
        if total_valid <= 0:
            return 0.0
        average_score = max(
            0.0,
            min(
                100.0,
                float(average_score),
            ),
        )
        agreement_ratio = (
            confirmations
            / total_valid
        )
        # До 30 баллов за согласованность.
        agreement_bonus = (
            agreement_ratio * 30.0
        )
        quality_score = min(
            100.0,
            average_score
            + agreement_bonus,
        )
        return quality_score
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
            "Quality evaluation started. "
            "Timeframes=%s",
            len(analyses),
        )
        # =================================================
        # EMPTY INPUT
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
        # VALID TIMEFRAMES
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
                total_checks=len(analyses),
                reasons=[],
                rejected_reasons=[
                    "Нет подтверждённых "
                    "таймфреймов."
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
                "Direction confirmation: "
                "UP=%s | DOWN=%s | VALID=%s"
            ),
            up_count,
            down_count,
            len(valid),
        )
        # =================================================
        # EQUAL DIRECTIONS
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
                total_checks=len(valid),
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
                "Недостаточно подтверждений "
                "по таймфреймам."
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
        # SELECT MATCHING TIMEFRAMES
        # =================================================
        selected = [
            item
            for item in valid
            if item.direction == direction
        ]
        if not selected:
            logger.warning(
                "No selected timeframes."
            )
            return QualityResult(
                accepted=False,
                direction=None,
                quality_score=0.0,
                confirmations=confirmations,
                total_checks=len(valid),
                reasons=[],
                rejected_reasons=[
                    "Не удалось выбрать "
                    "подтверждающие таймфреймы."
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
        # AGREEMENT RATIO
        # =================================================
        agreement_ratio = (
            confirmations
            / len(valid)
        )
        # =================================================
        # AGREEMENT BONUS
        # =================================================
        agreement_bonus = (
            agreement_ratio * 30.0
        )
        # =================================================
        # FINAL QUALITY
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
                "Качество ниже минимального "
                f"порога "
                f"{self.minimum_quality:.1f}%."
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
        # Удаляем дубликаты, сохраняя порядок.
        reasons = list(
            dict.fromkeys(
                reasons
            )
        )
        # =================================================
        # RESULT
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
# DEFAULT QUALITY FILTER
# =========================================================
quality_filter = QualityFilter(
    minimum_quality=70.0,
    minimum_confirmations=2,
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
