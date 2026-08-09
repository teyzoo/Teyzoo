from __future__ import annotations

from dataclasses import dataclass

from indicators import (
    calculate_indicators,
)

from market import Candle

from models import Direction


# ============================================================
# НАСТРОЙКИ
# ============================================================

MIN_CANDLES = 100

MIN_TIMEFRAME_SCORE = 80.0

MIN_TIMEFRAME_CONFIRMATIONS = 3

MIN_TIMEFRAME_AGREEMENT = 0.75

MIN_QUALITY_SCORE = 85.0


# ============================================================
# TIMEFRAME ANALYSIS
# ============================================================

@dataclass(slots=True)
class TimeframeAnalysis:

    timeframe: str

    direction: Direction | None

    score: float

    reasons: list[str]

    confirmations: int = 0

    total_checks: int = 0

    rejected: bool = False

    rejection_reason: str | None = None


# ============================================================
# QUALITY RESULT
# ============================================================

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


# ============================================================
# ANALYZE TIMEFRAME
# ============================================================

def analyze_timeframe(
    timeframe: str,
    candles: list[Candle],
) -> TimeframeAnalysis:

    # --------------------------------------------------------
    # Проверка данных
    # --------------------------------------------------------

    if len(candles) < MIN_CANDLES:

        return TimeframeAnalysis(
            timeframe=timeframe,
            direction=None,
            score=0.0,
            reasons=[
                "Недостаточно свечей."
            ],
            confirmations=0,
            total_checks=0,
            rejected=True,
            rejection_reason=(
                "Недостаточно свечей."
            ),
        )

    # --------------------------------------------------------
    # Индикаторы
    # --------------------------------------------------------

    try:

        indicators = (
            calculate_indicators(
                candles
            )
        )

    except Exception as exc:

        return TimeframeAnalysis(
            timeframe=timeframe,
            direction=None,
            score=0.0,
            reasons=[
                "Ошибка расчёта индикаторов."
            ],
            confirmations=0,
            total_checks=0,
            rejected=True,
            rejection_reason=str(exc),
        )

    bullish = 0

    bearish = 0

    checks = 0

    reasons: list[str] = []

    # ========================================================
    # EMA
    # ========================================================

    if (
        indicators.ema_fast is not None
        and indicators.ema_slow is not None
    ):

        checks += 1

        if (
            indicators.ema_fast
            > indicators.ema_slow
        ):

            bullish += 1

            reasons.append(
                "EMA подтверждает UP."
            )

        elif (
            indicators.ema_fast
            < indicators.ema_slow
        ):

            bearish += 1

            reasons.append(
                "EMA подтверждает DOWN."
            )

        else:

            reasons.append(
                "EMA нейтральна."
            )

    # ========================================================
    # MACD
    # ========================================================

    if (
        indicators.macd is not None
        and indicators.macd_signal is not None
    ):

        checks += 1

        if (
            indicators.macd
            > indicators.macd_signal
        ):

            bullish += 1

            reasons.append(
                "MACD подтверждает UP."
            )

        elif (
            indicators.macd
            < indicators.macd_signal
        ):

            bearish += 1

            reasons.append(
                "MACD подтверждает DOWN."
            )

        else:

            reasons.append(
                "MACD нейтрален."
            )

    # ========================================================
    # RSI
    # ========================================================

    if indicators.rsi is not None:

        checks += 1

        rsi = indicators.rsi

        if rsi < 30:

            bullish += 1

            reasons.append(
                f"RSI {rsi:.1f}: "
                "сильная перепроданность."
            )

        elif rsi > 70:

            bearish += 1

            reasons.append(
                f"RSI {rsi:.1f}: "
                "сильная перекупленность."
            )

        elif rsi < 40:

            bullish += 1

            reasons.append(
                f"RSI {rsi:.1f}: "
                "умеренная перепроданность."
            )

        elif rsi > 60:

            bearish += 1

            reasons.append(
                f"RSI {rsi:.1f}: "
                "умеренная перекупленность."
            )

        else:

            reasons.append(
                f"RSI {rsi:.1f}: нейтральный."
            )

    # ========================================================
    # BOLLINGER
    # ========================================================

    if (
        indicators.bollinger_upper is not None
        and indicators.bollinger_lower is not None
    ):

        checks += 1

        price = indicators.price

        upper = (
            indicators.bollinger_upper
        )

        lower = (
            indicators.bollinger_lower
        )

        if price <= lower:

            bullish += 1

            reasons.append(
                "Цена у нижней полосы Bollinger."
            )

        elif price >= upper:

            bearish += 1

            reasons.append(
                "Цена у верхней полосы Bollinger."
            )

        else:

            reasons.append(
                "Цена внутри Bollinger."
            )

    # ========================================================
    # НЕТ ПРОВЕРОК
    # ========================================================

    if checks == 0:

        return TimeframeAnalysis(
            timeframe=timeframe,
            direction=None,
            score=0.0,
            reasons=[
                *reasons,
                "Нет доступных проверок."
            ],
            confirmations=0,
            total_checks=0,
            rejected=True,
            rejection_reason=(
                "Нет индикаторов."
            ),
        )

    # ========================================================
    # КОНФЛИКТ
    # ========================================================

    if bullish == bearish:

        return TimeframeAnalysis(
            timeframe=timeframe,
            direction=None,
            score=0.0,
            reasons=[
                *reasons,
                "Индикаторы конфликтуют."
            ],
            confirmations=0,
            total_checks=checks,
            rejected=True,
            rejection_reason=(
                "Конфликт индикаторов."
            ),
        )

    # ========================================================
    # НАПРАВЛЕНИЕ
    # ========================================================

    if bullish > bearish:

        direction = Direction.UP

        confirmations = bullish

    else:

        direction = Direction.DOWN

        confirmations = bearish

    # ========================================================
    # SCORE
    # ========================================================

    score = (
        confirmations
        / checks
        * 100.0
    )

    # ========================================================
    # МАЛО ПОДТВЕРЖДЕНИЙ
    # ========================================================

    if (
        confirmations
        < MIN_TIMEFRAME_CONFIRMATIONS
    ):

        return TimeframeAnalysis(
            timeframe=timeframe,
            direction=None,
            score=score,
            reasons=[
                *reasons,
                (
                    "Недостаточно "
                    "подтверждений."
                ),
            ],
            confirmations=confirmations,
            total_checks=checks,
            rejected=True,
            rejection_reason=(
                "Недостаточно подтверждений."
            ),
        )

    # ========================================================
    # НИЗКИЙ SCORE
    # ========================================================

    if score < MIN_TIMEFRAME_SCORE:

        return TimeframeAnalysis(
            timeframe=timeframe,
            direction=None,
            score=score,
            reasons=[
                *reasons,
                (
                    "Score ниже минимального "
                    f"порога "
                    f"{MIN_TIMEFRAME_SCORE:.0f}%."
                ),
            ],
            confirmations=confirmations,
            total_checks=checks,
            rejected=True,
            rejection_reason=(
                "Низкий score."
            ),
        )

    # ========================================================
    # ПРОШЁЛ
    # ========================================================

    return TimeframeAnalysis(
        timeframe=timeframe,
        direction=direction,
        score=score,
        reasons=reasons,
        confirmations=confirmations,
        total_checks=checks,
        rejected=False,
        rejection_reason=None,
    )


# ============================================================
# QUALITY FILTER
# ============================================================

class QualityFilter:

    def __init__(
        self,
        minimum_quality: float = (
            MIN_QUALITY_SCORE
        ),
    ):

        self.minimum_quality = (
            minimum_quality
        )

    # ========================================================
    # EVALUATE
    # ========================================================

    def evaluate(
        self,
        analyses: list[
            TimeframeAnalysis
        ],
    ) -> QualityResult:

        rejected: list[str] = []

        reasons: list[str] = []

        # ----------------------------------------------------
        # Только прошедшие TF
        # ----------------------------------------------------

        valid = [
            item
            for item in analyses
            if (
                item.direction is not None
                and not item.rejected
            )
        ]

        # ----------------------------------------------------
        # Нет валидных TF
        # ----------------------------------------------------

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
                        "Нет таймфреймов, "
                        "прошедших фильтр."
                    )
                ],
                timeframe_results=analyses,
            )

        # ----------------------------------------------------
        # UP / DOWN
        # ----------------------------------------------------

        up_count = sum(
            1
            for item in valid
            if (
                item.direction
                == Direction.UP
            )
        )

        down_count = sum(
            1
            for item in valid
            if (
                item.direction
                == Direction.DOWN
            )
        )

        # ----------------------------------------------------
        # Определяем направление
        # ----------------------------------------------------

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
                total_checks=len(
                    valid
                ),
                reasons=[],
                rejected_reasons=[
                    (
                        "Таймфреймы "
                        "разделились поровну."
                    )
                ],
                timeframe_results=analyses,
            )

        # ----------------------------------------------------
        # Согласие таймфреймов
        # ----------------------------------------------------

        agreement = (
            confirmations
            / len(valid)
        )

        if (
            agreement
            < MIN_TIMEFRAME_AGREEMENT
        ):

            rejected.append(
                (
                    "Недостаточное согласие "
                    "таймфреймов: "
                    f"{agreement * 100:.1f}%."
                )
            )

        # ----------------------------------------------------
        # Выбираем TF направления
        # ----------------------------------------------------

        selected = [
            item
            for item in valid
            if (
                item.direction
                == direction
            )
        ]

        if not selected:

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
                    (
                        "Не найдено "
                        "подходящее направление."
                    )
                ],
                timeframe_results=analyses,
            )

        # ----------------------------------------------------
        # Средний score
        # ----------------------------------------------------

        average_score = (
            sum(
                item.score
                for item in selected
            )
            / len(selected)
        )

        # ----------------------------------------------------
        # Бонус за согласие
        # ----------------------------------------------------

        agreement_bonus = (
            agreement
            * 10.0
        )

        # ----------------------------------------------------
        # Финальный технический score
        # ----------------------------------------------------

        quality_score = min(
            100.0,
            average_score
            + agreement_bonus,
        )

        # ----------------------------------------------------
        # Причины
        # ----------------------------------------------------

        for item in selected:

            reasons.extend(
                item.reasons
            )

        # ----------------------------------------------------
        # Проверяем quality
        # ----------------------------------------------------

        if (
            quality_score
            < self.minimum_quality
        ):

            rejected.append(
                (
                    "Quality Score "
                    f"{quality_score:.1f}% "
                    "ниже минимального "
                    f"порога "
                    f"{self.minimum_quality:.1f}%."
                )
            )

        # ----------------------------------------------------
        # Конфликт
        # ----------------------------------------------------

        conflicting = [
            item
            for item in valid
            if (
                item.direction
                != direction
            )
        ]

        if conflicting:

            reasons.append(
                (
                    f"⚠️ "
                    f"{len(conflicting)} "
                    "таймфрейм(а) "
                    "не согласны "
                    "с основным направлением."
                )
            )

        # ----------------------------------------------------
        # Итог
        # ----------------------------------------------------

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
            reasons=reasons,
            rejected_reasons=rejected,
            timeframe_results=analyses,
        )


# ============================================================
# SINGLETON
# ============================================================

quality_filter = QualityFilter(
    minimum_quality=85.0
)
