from __future__ import annotations

from dataclasses import dataclass

from indicators import (
    IndicatorSnapshot,
    calculate_indicators,
)
from market import Candle
from models import Direction


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


def analyze_timeframe(
    timeframe: str,
    candles: list[Candle],
) -> TimeframeAnalysis:

    if len(candles) < 50:
        return TimeframeAnalysis(
            timeframe=timeframe,
            direction=None,
            score=0.0,
            reasons=[
                "Недостаточно свечей."
            ],
        )

    indicators = calculate_indicators(
        candles
    )

    bullish = 0
    bearish = 0

    reasons: list[str] = []

    # EMA
    if (
        indicators.ema_fast is not None
        and indicators.ema_slow is not None
    ):

        if (
            indicators.ema_fast
            > indicators.ema_slow
        ):
            bullish += 1
            reasons.append(
                "EMA bullish"
            )

        elif (
            indicators.ema_fast
            < indicators.ema_slow
        ):
            bearish += 1
            reasons.append(
                "EMA bearish"
            )

    # MACD
    if (
        indicators.macd is not None
        and indicators.macd_signal is not None
    ):

        if (
            indicators.macd
            > indicators.macd_signal
        ):
            bullish += 1
            reasons.append(
                "MACD bullish"
            )

        elif (
            indicators.macd
            < indicators.macd_signal
        ):
            bearish += 1
            reasons.append(
                "MACD bearish"
            )

    # RSI
    if indicators.rsi is not None:

        if indicators.rsi < 35:
            bullish += 1
            reasons.append(
                "RSI oversold"
            )

        elif indicators.rsi > 65:
            bearish += 1
            reasons.append(
                "RSI overbought"
            )

    # Bollinger
    if (
        indicators.bollinger_upper is not None
        and indicators.bollinger_lower is not None
    ):

        if (
            indicators.price
            <= indicators.bollinger_lower
        ):
            bullish += 1
            reasons.append(
                "Price near lower Bollinger band"
            )

        elif (
            indicators.price
            >= indicators.bollinger_upper
        ):
            bearish += 1
            reasons.append(
                "Price near upper Bollinger band"
            )

    total = bullish + bearish

    if total == 0:
        return TimeframeAnalysis(
            timeframe=timeframe,
            direction=None,
            score=0.0,
            reasons=[
                "Нет подтверждений."
            ],
        )

    if bullish > bearish:

        return TimeframeAnalysis(
            timeframe=timeframe,
            direction=Direction.UP,
            score=(
                bullish
                / total
                * 100
            ),
            reasons=reasons,
        )

    if bearish > bullish:

        return TimeframeAnalysis(
            timeframe=timeframe,
            direction=Direction.DOWN,
            score=(
                bearish
                / total
                * 100
            ),
            reasons=reasons,
        )

    return TimeframeAnalysis(
        timeframe=timeframe,
        direction=None,
        score=0.0,
        reasons=[
            "Конфликт индикаторов."
        ],
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
        analyses: list[TimeframeAnalysis],
    ) -> QualityResult:

        rejected: list[str] = []
        reasons: list[str] = []

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
            1
            for item in valid
            if item.direction == Direction.UP
        )

        down_count = sum(
            1
            for item in valid
            if item.direction == Direction.DOWN
        )

        # Если направления конфликтуют слишком сильно —
        # сделку пропускаем.
        if up_count and down_count:

            rejected.append(
                "Таймфреймы конфликтуют."
            )

        if up_count > down_count:
            direction = Direction.UP
            confirmations = up_count

        elif down_count > up_count:
            direction = Direction.DOWN
            confirmations = down_count

        else:

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

        # Для максимально строгого режима
        # требуем минимум 2 подтверждённых TF.
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

        if not selected:

            return QualityResult(
                accepted=False,
                direction=None,
                quality_score=0.0,
                confirmations=0,
                total_checks=len(valid),
                reasons=[],
                rejected_reasons=[
                    "Нет подходящего направления."
                ],
                timeframe_results=analyses,
            )

        average_score = (
            sum(
                item.score
                for item in selected
            )
            / len(selected)
        )

        # Дополнительный бонус за согласие TF.
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

        reasons.extend(
            item.reasons
            for item in selected
        )

        # Если качество ниже порога.
        if quality_score < self.minimum_quality:

            rejected.append(
                "Качество ниже минимального "
                f"порога {self.minimum_quality:.0f}%."
            )

        # Если есть конфликт — сигнал запрещаем.
        accepted = (
            len(rejected) == 0
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
            reasons=[
                reason
                for group in reasons
                for reason in (
                    group
                    if isinstance(group, list)
                    else [group]
                )
            ],
            rejected_reasons=rejected,
            timeframe_results=analyses,
        )


quality_filter = QualityFilter(
    minimum_quality=85.0
)
