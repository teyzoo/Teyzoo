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
# HELPERS
# =========================================================


def _safe_score(value: object) -> float:
    """
    Безопасно приводит score к диапазону 0..100.
    """

    try:
        score = float(value)
    except (
        TypeError,
        ValueError,
        OverflowError,
    ):
        return 0.0

    if score < 0.0:
        return 0.0

    if score > 100.0:
        return 100.0

    return score


def _safe_reasons(
    reasons: object,
) -> list[str]:
    """
    Преобразует причины SignalEngine в безопасный список.
    """

    if reasons is None:
        return []

    if isinstance(reasons, str):
        return [reasons]

    try:
        return [
            str(reason)
            for reason in reasons
            if reason is not None
        ]
    except TypeError:
        return [str(reasons)]


def _deduplicate_reasons(
    reasons: list[str],
) -> list[str]:
    """
    Удаляет дубликаты, сохраняя порядок.
    """

    return list(
        dict.fromkeys(
            reason
            for reason in reasons
            if reason
        )
    )


# =========================================================
# TIMEFRAME ANALYSIS
# =========================================================


def analyze_timeframe(
    timeframe: str,
    candles: list[Candle],
) -> TimeframeAnalysis:
    """
    Анализирует один таймфрейм через SignalEngine.

    MarketClient уже отвечает за получение свечей.
    Здесь мы работаем только с готовым списком Candle.
    """

    normalized_timeframe = str(
        timeframe
    ).strip()

    if not normalized_timeframe:
        raise ValueError(
            "Timeframe is required."
        )

    if not candles:
        logger.warning(
            "Timeframe %s contains no candles.",
            normalized_timeframe,
        )

        return TimeframeAnalysis(
            timeframe=normalized_timeframe,
            direction=None,
            score=0.0,
            reasons=[
                "Нет свечей для анализа."
            ],
        )

    if len(candles) < 20:
        logger.warning(
            (
                "Timeframe %s has too few candles: "
                "%s."
            ),
            normalized_timeframe,
            len(candles),
        )

        return TimeframeAnalysis(
            timeframe=normalized_timeframe,
            direction=None,
            score=0.0,
            reasons=[
                (
                    "Недостаточно свечей "
                    f"для анализа: {len(candles)}."
                )
            ],
        )

    try:
        result = signal_engine.analyze(
            candles
        )

    except Exception as exc:
        logger.exception(
            (
                "SignalEngine failed for "
                "timeframe=%s: %s"
            ),
            normalized_timeframe,
            exc,
        )

        return TimeframeAnalysis(
            timeframe=normalized_timeframe,
            direction=None,
            score=0.0,
            reasons=[
                "Ошибка анализа таймфрейма."
            ],
        )

    direction = getattr(
        result,
        "direction",
        None,
    )

    score = _safe_score(
        getattr(
            result,
            "score",
            0.0,
        )
    )

    reasons = _safe_reasons(
        getattr(
            result,
            "reasons",
            [],
        )
    )

    logger.info(
        (
            "Timeframe %s | "
            "candles=%s | "
            "direction=%s | "
            "score=%.2f | "
            "confirmations=%s/%s | "
            "reasons=%s"
        ),
        normalized_timeframe,
        len(candles),
        direction,
        score,
        getattr(
            result,
            "confirmations",
            0,
        ),
        getattr(
            result,
            "total_checks",
            0,
        ),
        reasons,
    )

    return TimeframeAnalysis(
        timeframe=normalized_timeframe,
        direction=direction,
        score=score,
        reasons=reasons,
    )


# =========================================================
# QUALITY FILTER
# =========================================================


class QualityFilter:
    """
    Финальный multi-timeframe фильтр.

    Алгоритм:

    1. Получаем результаты всех таймфреймов.
    2. Убираем таймфреймы без направления.
    3. Считаем UP и DOWN.
    4. Определяем доминирующее направление.
    5. Проверяем минимальное количество подтверждений.
    6. Считаем средний score выбранного направления.
    7. Добавляем бонус за согласованность TF.
    8. Проверяем минимальный Quality Score.
    9. Возвращаем итоговый QualityResult.
    """

    def __init__(
        self,
        minimum_quality: float = 60.0,
        minimum_confirmations: int = 2,
        full_agreement_bonus: float = 10.0,
        majority_bonus: float = 5.0,
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
        """
        Рассчитывает итоговый Quality Score.
        """

        if total_valid <= 0:
            return 0.0

        average_score = _safe_score(
            average_score
        )

        confirmations = max(
            0,
            int(confirmations),
        )

        total_valid = max(
            1,
            int(total_valid),
        )

        agreement_ratio = (
            confirmations
            / total_valid
        )

        if confirmations == total_valid:
            bonus = (
                self.full_agreement_bonus
            )

        elif agreement_ratio >= 0.66:
            bonus = (
                self.majority_bonus
            )

        else:
            bonus = 0.0

        quality_score = (
            average_score
            + bonus
        )

        return min(
            100.0,
            max(
                0.0,
                quality_score,
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
                "timeframes=%s"
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
        # NORMALIZE ANALYSES
        # =================================================

        normalized_analyses: list[
            TimeframeAnalysis
        ] = []

        for analysis in analyses:

            if not isinstance(
                analysis,
                TimeframeAnalysis,
            ):
                logger.warning(
                    (
                        "Ignoring invalid "
                        "timeframe analysis: %r"
                    ),
                    analysis,
                )
                continue

            normalized_analyses.append(
                analysis
            )

        if not normalized_analyses:

            logger.info(
                "Quality rejected: "
                "no valid timeframe analyses."
            )

            return QualityResult(
                accepted=False,
                direction=None,
                quality_score=0.0,
                confirmations=0,
                total_checks=0,
                reasons=[],
                rejected_reasons=[
                    "Нет корректных результатов анализа."
                ],
                timeframe_results=[],
            )

        # =================================================
        # VALID TIMEFRAMES
        # =================================================

        valid = [
            analysis
            for analysis in normalized_analyses
            if analysis.direction is not None
        ]

        logger.info(
            (
                "Valid timeframe analyses: "
                "%s/%s"
            ),
            len(valid),
            len(normalized_analyses),
        )

        if not valid:

            logger.info(
                "Quality rejected: "
                "no timeframe has direction."
            )

            return QualityResult(
                accepted=False,
                direction=None,
                quality_score=0.0,
                confirmations=0,
                total_checks=len(
                    normalized_analyses
                ),
                reasons=[],
                rejected_reasons=[
                    "Нет подтверждённых таймфреймов."
                ],
                timeframe_results=normalized_analyses,
            )

        # =================================================
        # COUNT DIRECTIONS
        # =================================================

        up_count = sum(
            analysis.direction
            == Direction.UP
            for analysis in valid
        )

        down_count = sum(
            analysis.direction
            == Direction.DOWN
            for analysis in valid
        )

        logger.info(
            (
                "Direction confirmation | "
                "UP=%s | "
                "DOWN=%s | "
                "VALID=%s"
            ),
            up_count,
            down_count,
            len(valid),
        )

        # =================================================
        # INVALID / UNKNOWN DIRECTIONS
        # =================================================

        known_directions = {
            Direction.UP,
            Direction.DOWN,
        }

        known = [
            analysis
            for analysis in valid
            if analysis.direction
            in known_directions
        ]

        if not known:

            logger.info(
                "Quality rejected: "
                "no recognized directions."
            )

            return QualityResult(
                accepted=False,
                direction=None,
                quality_score=0.0,
                confirmations=0,
                total_checks=len(valid),
                reasons=[],
                rejected_reasons=[
                    "Не удалось определить направление."
                ],
                timeframe_results=normalized_analyses,
            )

        # =================================================
        # CONFLICT
        # =================================================

        if up_count == down_count:

            logger.info(
                (
                    "Quality rejected: "
                    "direction conflict "
                    "UP=%s DOWN=%s"
                ),
                up_count,
                down_count,
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
                timeframe_results=normalized_analyses,
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
                "Selected direction | "
                "direction=%s | "
                "confirmations=%s/%s"
            ),
            direction,
            confirmations,
            len(valid),
        )

        # =================================================
        # SELECT MATCHING TIMEFRAMES
        # =================================================

        selected = [
            analysis
            for analysis in valid
            if analysis.direction
            == direction
        ]

        if not selected:

            logger.error(
                (
                    "Quality filter internal error: "
                    "selected direction has no analyses."
                )
            )

            return QualityResult(
                accepted=False,
                direction=None,
                quality_score=0.0,
                confirmations=confirmations,
                total_checks=len(valid),
                reasons=[],
                rejected_reasons=[
                    (
                        "Не удалось выбрать "
                        "подтверждающие таймфреймы."
                    )
                ],
                timeframe_results=normalized_analyses,
            )

        # =================================================
        # MINIMUM CONFIRMATIONS
        # =================================================

        rejected: list[str] = []

        if confirmations < (
            self.minimum_confirmations
        ):

            rejected.append(
                (
                    "Недостаточно подтверждений "
                    "по таймфреймам: "
                    f"{confirmations}/"
                    f"{self.minimum_confirmations}."
                )
            )

            logger.info(
                (
                    "Quality rejected by confirmations | "
                    "confirmations=%s | "
                    "minimum=%s"
                ),
                confirmations,
                self.minimum_confirmations,
            )

        # =================================================
        # AVERAGE SCORE
        # =================================================

        if selected:

            average_score = (
                sum(
                    _safe_score(
                        analysis.score
                    )
                    for analysis in selected
                )
                / len(selected)
            )

        else:

            average_score = 0.0

        # =================================================
        # AGREEMENT
        # =================================================

        agreement_ratio = (
            confirmations
            / len(valid)
        )

        # =================================================
        # AGREEMENT BONUS
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
                "Quality calculation | "
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
                    "Quality rejected by score | "
                    "quality=%.2f | "
                    "minimum=%.2f"
                ),
                quality_score,
                self.minimum_quality,
            )

        # =================================================
        # REASONS
        # =================================================

        reasons: list[str] = []

        for analysis in selected:

            reasons.extend(
                analysis.reasons
            )

        reasons = _deduplicate_reasons(
            reasons
        )

        # =================================================
        # QUALITY REASONS
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
                "Согласованность TF: "
                f"{agreement_ratio * 100.0:.1f}%"
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

        accepted = (
            len(rejected) == 0
        )

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
                    "direction=%s | "
                    "score=%.2f | "
                    "confirmations=%s/%s | "
                    "reasons=%s"
                ),
                direction,
                quality_score,
                confirmations,
                len(valid),
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
            timeframe_results=normalized_analyses,
        )


# =========================================================
# DEFAULT QUALITY FILTER
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
