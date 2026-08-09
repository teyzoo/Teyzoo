from __future__ import annotations

from dataclasses import dataclass

from market import Candle
from models import Direction
from signal_engine import (
    signal_engine,
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

        valid = [
            item
            for item in analyses
            if item.direction is not None
        ]

        if not valid:

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

        up_count = sum(
            item.direction == Direction.UP
            for item in valid
        )

        down_count = sum(
            item.direction == Direction.DOWN
            for item in valid
        )

        if up_count == down_count:

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

        if up_count > down_count:

            direction = Direction.UP
            confirmations = up_count

        else:

            direction = Direction.DOWN
            confirmations = down_count

        if confirmations < 2:

            rejected.append(
                "Недостаточно подтверждений "
                "по таймфреймам."
            )

        selected = [
            item
            for item in valid
            if item.direction == direction
        ]

        average_score = (
            sum(
                item.score
                for item in selected
            )
            / len(selected)
        )

        agreement_bonus = (
            confirmations
            / len(valid)
            * 10
        )

        quality_score = min(
            100.0,
            average_score
            + agreement_bonus,
        )

        if quality_score < (
            self.minimum_quality
        ):

            rejected.append(
                "Качество ниже минимального "
                f"порога "
                f"{self.minimum_quality:.1f}%."
            )

        reasons: list[str] = []

        for item in selected:

            reasons.extend(
                item.reasons
            )

        return QualityResult(
            accepted=not rejected,
            direction=(
                direction
                if not rejected
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
