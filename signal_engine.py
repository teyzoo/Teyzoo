from __future__ import annotations
from dataclasses import dataclass
from indicators import calculate_indicators
from market import Candle
from models import Direction
@dataclass(slots=True)
class AnalysisResult:
    direction: Direction | None
    score: float
    reasons: list[str]
    confirmations: int
    total_checks: int
class SignalEngine:
    """
    Основной движок анализа одного таймфрейма.
    Индикаторы:
        EMA       = 25%
        RSI       = 25%
        MACD      = 30%
        Bollinger = 20%
    ВАЖНО:
    Нейтральный индикатор не считается
    отрицательным сигналом.
    Например:
        EMA bullish
        MACD bullish
        RSI neutral
        Bollinger neutral
    даст:
        25 + 30 = 55%
    а не 50% из-за деления
    на все 4 проверки.
    Это позволяет score показывать
    реальную силу направленных сигналов.
    """
    # =====================================================
    # WEIGHTS
    # =====================================================
    EMA_WEIGHT = 25.0
    RSI_WEIGHT = 25.0
    MACD_WEIGHT = 30.0
    BOLLINGER_WEIGHT = 20.0
    # Минимальное количество свечей
    MIN_CANDLES = 50
    # =====================================================
    # ANALYZE
    # =====================================================
    def analyze(
        self,
        candles: list[Candle],
    ) -> AnalysisResult:
        # =================================================
        # CANDLES
        # =================================================
        if len(candles) < self.MIN_CANDLES:
            return AnalysisResult(
                direction=None,
                score=0.0,
                reasons=[
                    (
                        "Недостаточно свечей: "
                        f"{len(candles)}/{self.MIN_CANDLES}."
                    )
                ],
                confirmations=0,
                total_checks=0,
            )
        # =================================================
        # INDICATORS
        # =================================================
        try:
            indicators = calculate_indicators(
                candles
            )
        except Exception as exc:
            return AnalysisResult(
                direction=None,
                score=0.0,
                reasons=[
                    (
                        "Ошибка расчёта "
                        f"индикаторов: {exc}"
                    )
                ],
                confirmations=0,
                total_checks=0,
            )
        # =================================================
        # COUNTERS
        # =================================================
        bullish_score = 0.0
        bearish_score = 0.0
        bullish_confirmations = 0
        bearish_confirmations = 0
        reasons: list[str] = []
        total_checks = 0
        # =================================================
        # EMA
        # =================================================
        if (
            indicators.ema_fast is not None
            and indicators.ema_slow is not None
        ):
            total_checks += 1
            if (
                indicators.ema_fast
                > indicators.ema_slow
            ):
                bullish_score += self.EMA_WEIGHT
                bullish_confirmations += 1
                reasons.append(
                    (
                        "EMA: bullish "
                        f"({self.EMA_WEIGHT:.0f}%)"
                    )
                )
            elif (
                indicators.ema_fast
                < indicators.ema_slow
            ):
                bearish_score += self.EMA_WEIGHT
                bearish_confirmations += 1
                reasons.append(
                    (
                        "EMA: bearish "
                        f"({self.EMA_WEIGHT:.0f}%)"
                    )
                )
            else:
                reasons.append(
                    "EMA: neutral"
                )
        # =================================================
        # RSI
        # =================================================
        if indicators.rsi is not None:
            total_checks += 1
            rsi = float(
                indicators.rsi
            )
            if rsi <= 35.0:
                bullish_score += self.RSI_WEIGHT
                bullish_confirmations += 1
                reasons.append(
                    (
                        "RSI: oversold "
                        f"({rsi:.1f}) "
                        f"+{self.RSI_WEIGHT:.0f}%"
                    )
                )
            elif rsi >= 65.0:
                bearish_score += self.RSI_WEIGHT
                bearish_confirmations += 1
                reasons.append(
                    (
                        "RSI: overbought "
                        f"({rsi:.1f}) "
                        f"+{self.RSI_WEIGHT:.0f}%"
                    )
                )
            else:
                reasons.append(
                    f"RSI: neutral ({rsi:.1f})"
                )
        # =================================================
        # MACD
        # =================================================
        if (
            indicators.macd is not None
            and indicators.macd_signal is not None
        ):
            total_checks += 1
            if (
                indicators.macd
                > indicators.macd_signal
            ):
                bullish_score += self.MACD_WEIGHT
                bullish_confirmations += 1
                reasons.append(
                    (
                        "MACD: bullish "
                        f"({self.MACD_WEIGHT:.0f}%)"
                    )
                )
            elif (
                indicators.macd
                < indicators.macd_signal
            ):
                bearish_score += self.MACD_WEIGHT
                bearish_confirmations += 1
                reasons.append(
                    (
                        "MACD: bearish "
                        f"({self.MACD_WEIGHT:.0f}%)"
                    )
                )
            else:
                reasons.append(
                    "MACD: neutral"
                )
        # =================================================
        # BOLLINGER
        # =================================================
        if (
            indicators.bollinger_upper is not None
            and indicators.bollinger_lower is not None
        ):
            total_checks += 1
            price = float(
                indicators.price
            )
            upper = float(
                indicators.bollinger_upper
            )
            lower = float(
                indicators.bollinger_lower
            )
            if price <= lower:
                bullish_score += (
                    self.BOLLINGER_WEIGHT
                )
                bullish_confirmations += 1
                reasons.append(
                    (
                        "Bollinger: lower band "
                        f"({self.BOLLINGER_WEIGHT:.0f}%)"
                    )
                )
            elif price >= upper:
                bearish_score += (
                    self.BOLLINGER_WEIGHT
                )
                bearish_confirmations += 1
                reasons.append(
                    (
                        "Bollinger: upper band "
                        f"({self.BOLLINGER_WEIGHT:.0f}%)"
                    )
                )
            else:
                reasons.append(
                    "Bollinger: neutral"
                )
        # =================================================
        # NO INDICATORS
        # =================================================
        if total_checks == 0:
            return AnalysisResult(
                direction=None,
                score=0.0,
                reasons=[
                    "Индикаторы не рассчитаны."
                ],
                confirmations=0,
                total_checks=0,
            )
        # =================================================
        # CONFLICT
        # =================================================
        if (
            bullish_score == 0.0
            and bearish_score == 0.0
        ):
            return AnalysisResult(
                direction=None,
                score=0.0,
                reasons=[
                    *reasons,
                    "Нет направленных подтверждений.",
                ],
                confirmations=0,
                total_checks=total_checks,
            )
        # =================================================
        # EQUAL SCORES
        # =================================================
        if (
            abs(
                bullish_score
                - bearish_score
            )
            < 0.000001
        ):
            return AnalysisResult(
                direction=None,
                score=0.0,
                reasons=[
                    *reasons,
                    "Индикаторы дают конфликтующий сигнал.",
                ],
                confirmations=0,
                total_checks=total_checks,
            )
        # =================================================
        # UP
        # =================================================
        if bullish_score > bearish_score:
            direction = Direction.UP
            score = bullish_score
            confirmations = (
                bullish_confirmations
            )
            conflict_score = (
                bearish_score
            )
            dominant_score = (
                bullish_score
            )
        # =================================================
        # DOWN
        # =================================================
        else:
            direction = Direction.DOWN
            score = bearish_score
            confirmations = (
                bearish_confirmations
            )
            conflict_score = (
                bullish_score
            )
            dominant_score = (
                bearish_score
            )
        # =================================================
        # DIRECTION STRENGTH
        # =================================================
        direction_strength = (
            dominant_score / 100.0
        )
        # =================================================
        # ADVANTAGE
        # =================================================
        total_direction_score = (
            dominant_score
            + conflict_score
        )
        if total_direction_score > 0:
            advantage = (
                dominant_score
                / total_direction_score
                * 100.0
            )
        else:
            advantage = 0.0
        # =================================================
        # REASONS
        # =================================================
        reasons.append(
            (
                "Итоговое направление: "
                f"{direction.value}"
            )
        )
        reasons.append(
            (
                "Сила направления: "
                f"{direction_strength:.2f}"
            )
        )
        reasons.append(
            (
                "Конфликтующая сила: "
                f"{conflict_score / 100.0:.2f}"
            )
        )
        reasons.append(
            (
                "Преимущество направления: "
                f"{advantage:.1f}%"
            )
        )
        reasons.append(
            (
                "Итоговый score: "
                f"{score:.1f}%"
            )
        )
        # =================================================
        # RETURN
        # =================================================
        return AnalysisResult(
            direction=direction,
            score=min(
                100.0,
                max(
                    0.0,
                    score,
                ),
            ),
            reasons=reasons,
            confirmations=confirmations,
            total_checks=total_checks,
        )
# =========================================================
# SINGLETON
# =========================================================
signal_engine = SignalEngine()
# =========================================================
# EXPORTS
# =========================================================
__all__ = [
    "AnalysisResult",
    "SignalEngine",
    "signal_engine",
]
