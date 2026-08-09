from __future__ import annotations
import logging
from dataclasses import dataclass
from market import Candle
from models import Direction
from signal_engine import (
    signal_engine,
)
logger = logging.getLogger(
    "quality_filter"
)
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
        reasons=result.reasons,
    )
class QualityFilter:
    def __init__(
        self,
        minimum_quality: float = 85.0,
    ):
        self.minimum_quality = (
            minimum_quality
        )
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
        if confirmations < 2:
            rejected.append(
                "Недостаточно подтверждений "
                "по таймфреймам."
            )
            logger.info(
                "Rejected: confirmations=%s < 2",
                confirmations,
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
        # AGREEMENT BONUS
        # =================================================
        agreement_bonus = (
            confirmations
            / len(valid)
            * 10
        )
        # =================================================
        # FINAL QUALITY
        # =================================================
        quality_score = min(
            100.0,
            average_score
            + agreement_bonus,
        )
        logger.info(
            (
                "Quality calculation: "
                "average=%.2f | "
                "bonus=%.2f | "
                "final=%.2f | "
                "minimum=%.2f"
            ),
            average_score,
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
quality_filter = QualityFilter(
    minimum_quality=85.0
)
