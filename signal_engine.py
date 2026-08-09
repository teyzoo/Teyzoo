from __future__ import annotations

from dataclasses import dataclass

from indicators import (
    calculate_indicators,
)

from market import Candle

from models import Direction


# ============================================================
# НАСТРОЙКИ SIGNAL ENGINE
# ============================================================

MIN_CANDLES = 100

# Минимальная доля подтверждений.
#
# ВАЖНО:
# Это НЕ вероятность выигрыша.
# Это внутренняя техническая уверенность
# модели по имеющимся индикаторам.
MIN_TECHNICAL_SCORE = 80.0

# Минимальное количество подтверждений.
MIN_CONFIRMATIONS = 3

# Максимальная разница между направлениями,
# при которой мы считаем рынок слишком
# конфликтным.
MAX_CONFLICT_RATIO = 0.70


# ============================================================
# РЕЗУЛЬТАТ
# ============================================================

@dataclass(slots=True)
class AnalysisResult:

    direction: Direction | None

    score: float

    reasons: list[str]

    confirmations: int

    total_checks: int

    # Дополнительная информация
    bullish_checks: int = 0

    bearish_checks: int = 0

    rejected: bool = False

    rejection_reason: str | None = None


# ============================================================
# SIGNAL ENGINE
# ============================================================

class SignalEngine:

    def analyze(
        self,
        candles: list[Candle],
    ) -> AnalysisResult:

        # ----------------------------------------------------
        # 1. Проверка количества свечей
        # ----------------------------------------------------

        if len(candles) < MIN_CANDLES:

            return AnalysisResult(
                direction=None,
                score=0.0,
                reasons=[
                    (
                        "Недостаточно исторических "
                        "данных для анализа."
                    )
                ],
                confirmations=0,
                total_checks=0,
                rejected=True,
                rejection_reason=(
                    "Недостаточно свечей."
                ),
            )

        # ----------------------------------------------------
        # 2. Расчёт индикаторов
        # ----------------------------------------------------

        try:

            indicators = calculate_indicators(
                candles
            )

        except Exception as exc:

            return AnalysisResult(
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

        reasons: list[str] = []

        checks = 0

        # ----------------------------------------------------
        # 3. EMA TREND
        # ----------------------------------------------------

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
                    "EMA подтверждает восходящий тренд."
                )

            elif (
                indicators.ema_fast
                < indicators.ema_slow
            ):

                bearish += 1

                reasons.append(
                    "EMA подтверждает нисходящий тренд."
                )

            else:

                reasons.append(
                    "EMA не показывает направления."
                )

        # ----------------------------------------------------
        # 4. RSI
        # ----------------------------------------------------

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

            elif 40 <= rsi <= 60:

                reasons.append(
                    f"RSI {rsi:.1f}: "
                    "нейтральная зона."
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

        # ----------------------------------------------------
        # 5. MACD
        # ----------------------------------------------------

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
                    "MACD подтверждает бычье движение."
                )

            elif (
                indicators.macd
                < indicators.macd_signal
            ):

                bearish += 1

                reasons.append(
                    "MACD подтверждает медвежье движение."
                )

            else:

                reasons.append(
                    "MACD не показывает направления."
                )

        # ----------------------------------------------------
        # 6. BOLLINGER BANDS
        # ----------------------------------------------------

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
                    "Цена внутри диапазона Bollinger."
                )

        # ----------------------------------------------------
        # 7. НЕТ ИНДИКАТОРОВ
        # ----------------------------------------------------

        if checks == 0:

            return AnalysisResult(
                direction=None,
                score=0.0,
                reasons=[
                    "Индикаторы не рассчитаны."
                ],
                confirmations=0,
                total_checks=0,
                rejected=True,
                rejection_reason=(
                    "Нет доступных индикаторов."
                ),
            )

        # ----------------------------------------------------
        # 8. ПОЛНЫЙ КОНФЛИКТ
        # ----------------------------------------------------

        if bullish == bearish:

            return AnalysisResult(
                direction=None,
                score=0.0,
                reasons=[
                    *reasons,
                    (
                        "Индикаторы не имеют "
                        "единого направления."
                    ),
                ],
                confirmations=0,
                total_checks=checks,
                bullish_checks=bullish,
                bearish_checks=bearish,
                rejected=True,
                rejection_reason=(
                    "Конфликт направлений."
                ),
            )

        # ----------------------------------------------------
        # 9. ОПРЕДЕЛЯЕМ НАПРАВЛЕНИЕ
        # ----------------------------------------------------

        if bullish > bearish:

            direction = Direction.UP

            confirmations = bullish

        else:

            direction = Direction.DOWN

            confirmations = bearish

        # ----------------------------------------------------
        # 10. ТЕХНИЧЕСКИЙ SCORE
        # ----------------------------------------------------

        score = (
            confirmations
            / checks
            * 100.0
        )

        # ----------------------------------------------------
        # 11. ПРОВЕРКА КОНФЛИКТА
        # ----------------------------------------------------

        dominant = max(
            bullish,
            bearish,
        )

        conflict_ratio = (
            dominant / checks
        )

        if (
            conflict_ratio
            < MAX_CONFLICT_RATIO
        ):

            return AnalysisResult(
                direction=None,
                score=score,
                reasons=[
                    *reasons,
                    (
                        "Слишком сильный конфликт "
                        "между индикаторами."
                    ),
                ],
                confirmations=confirmations,
                total_checks=checks,
                bullish_checks=bullish,
                bearish_checks=bearish,
                rejected=True,
                rejection_reason=(
                    "Сильный конфликт индикаторов."
                ),
            )

        # ----------------------------------------------------
        # 12. МАЛО ПОДТВЕРЖДЕНИЙ
        # ----------------------------------------------------

        if confirmations < MIN_CONFIRMATIONS:

            return AnalysisResult(
                direction=None,
                score=score,
                reasons=[
                    *reasons,
                    (
                        "Недостаточно подтверждений "
                        "для безопасной выдачи сигнала."
                    ),
                ],
                confirmations=confirmations,
                total_checks=checks,
                bullish_checks=bullish,
                bearish_checks=bearish,
                rejected=True,
                rejection_reason=(
                    "Недостаточно подтверждений."
                ),
            )

        # ----------------------------------------------------
        # 13. НИЗКИЙ TECHNICAL SCORE
        # ----------------------------------------------------

        if score < MIN_TECHNICAL_SCORE:

            return AnalysisResult(
                direction=None,
                score=score,
                reasons=[
                    *reasons,
                    (
                        "Техническая уверенность "
                        "ниже установленного порога."
                    ),
                ],
                confirmations=confirmations,
                total_checks=checks,
                bullish_checks=bullish,
                bearish_checks=bearish,
                rejected=True,
                rejection_reason=(
                    "Низкий технический score."
                ),
            )

        # ----------------------------------------------------
        # 14. СИГНАЛ ПРОШЁЛ
        # ----------------------------------------------------

        reasons.insert(
            0,
            (
                "Сигнал имеет "
                f"{confirmations}/{checks} "
                "технических подтверждений."
            ),
        )

        return AnalysisResult(
            direction=direction,
            score=score,
            reasons=reasons,
            confirmations=confirmations,
            total_checks=checks,
            bullish_checks=bullish,
            bearish_checks=bearish,
            rejected=False,
            rejection_reason=None,
        )


# ============================================================
# SINGLETON
# ============================================================

signal_engine = SignalEngine()
