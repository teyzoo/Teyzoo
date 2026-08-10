from __future__ import annotations
from dataclasses import dataclass
from indicators import calculate_indicators
from market import Candle
from models import Direction
# =========================================================
# ANALYSIS RESULT
# =========================================================
@dataclass(slots=True)
class AnalysisResult:
    direction: Direction | None
    score: float
    reasons: list[str]
    confirmations: int
    total_checks: int
# =========================================================
# SIGNAL ENGINE
# =========================================================
class SignalEngine:
    """
    Основной движок анализа торгового сигнала.
    Использует:
        • EMA
        • RSI
        • MACD
        • Bollinger Bands
    В отличие от старой версии, score больше не является
    только 25 / 50 / 75 / 100.
    Каждый индикатор имеет силу от 0 до 1.
    Итоговый score рассчитывается по фактической силе
    подтверждений.
    ВАЖНО:
        score != гарантия прибыльности.
    Это внутренняя оценка силы технического сигнала.
    """
    # -----------------------------------------------------
    # Минимальное количество свечей
    # -----------------------------------------------------
    MIN_CANDLES = 50
    # -----------------------------------------------------
    # Минимальная разница между bullish и bearish
    # -----------------------------------------------------
    #
    # Если разница слишком маленькая, рынок считается
    # неопределённым.
    #
    # Например:
    #
    # bullish = 0.95
    # bearish = 0.90
    #
    # Это не достаточно сильное преимущество.
    #
    MIN_DIRECTION_ADVANTAGE = 0.08
    # -----------------------------------------------------
    # Минимальная сила одного индикатора
    # -----------------------------------------------------
    MIN_INDICATOR_STRENGTH = 0.15
    # -----------------------------------------------------
    # Веса индикаторов
    # -----------------------------------------------------
    EMA_WEIGHT = 1.00
    RSI_WEIGHT = 1.00
    MACD_WEIGHT = 1.10
    BOLLINGER_WEIGHT = 0.90
    # =====================================================
    # ANALYZE
    # =====================================================
    def analyze(
        self,
        candles: list[Candle],
    ) -> AnalysisResult:
        # -------------------------------------------------
        # CANDLE VALIDATION
        # -------------------------------------------------
        if len(candles) < self.MIN_CANDLES:
            return AnalysisResult(
                direction=None,
                score=0.0,
                reasons=[
                    "Недостаточно свечей."
                ],
                confirmations=0,
                total_checks=0,
            )
        # -------------------------------------------------
        # INDICATORS
        # -------------------------------------------------
        try:
            indicators = calculate_indicators(
                candles
            )
        except Exception:
            return AnalysisResult(
                direction=None,
                score=0.0,
                reasons=[
                    "Ошибка расчёта индикаторов."
                ],
                confirmations=0,
                total_checks=0,
            )
        # -------------------------------------------------
        # ACCUMULATORS
        # -------------------------------------------------
        bullish_strength = 0.0
        bearish_strength = 0.0
        bullish_confirmations = 0
        bearish_confirmations = 0
        checks = 0
        reasons: list[str] = []
        # =================================================
        # EMA
        # =================================================
        if (
            indicators.ema_fast is not None
            and indicators.ema_slow is not None
        ):
            checks += 1
            ema_fast = float(
                indicators.ema_fast
            )
            ema_slow = float(
                indicators.ema_slow
            )
            # ---------------------------------------------
            # BULLISH
            # ---------------------------------------------
            if ema_fast > ema_slow:
                difference = abs(
                    ema_fast - ema_slow
                )
                base_price = abs(
                    float(
                        indicators.price
                    )
                )
                if base_price > 0:
                    relative_difference = (
                        difference
                        / base_price
                    )
                else:
                    relative_difference = 0.0
                strength = min(
                    1.0,
                    max(
                        0.20,
                        relative_difference
                        * 100.0,
                    ),
                )
                bullish_strength += (
                    strength
                    * self.EMA_WEIGHT
                )
                if strength >= (
                    self.MIN_INDICATOR_STRENGTH
                ):
                    bullish_confirmations += 1
                reasons.append(
                    (
                        "EMA: bullish "
                        f"({strength * 100:.0f}%)"
                    )
                )
            # ---------------------------------------------
            # BEARISH
            # ---------------------------------------------
            elif ema_fast < ema_slow:
                difference = abs(
                    ema_fast - ema_slow
                )
                base_price = abs(
                    float(
                        indicators.price
                    )
                )
                if base_price > 0:
                    relative_difference = (
                        difference
                        / base_price
                    )
                else:
                    relative_difference = 0.0
                strength = min(
                    1.0,
                    max(
                        0.20,
                        relative_difference
                        * 100.0,
                    ),
                )
                bearish_strength += (
                    strength
                    * self.EMA_WEIGHT
                )
                if strength >= (
                    self.MIN_INDICATOR_STRENGTH
                ):
                    bearish_confirmations += 1
                reasons.append(
                    (
                        "EMA: bearish "
                        f"({strength * 100:.0f}%)"
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
            checks += 1
            rsi = float(
                indicators.rsi
            )
            # ---------------------------------------------
            # STRONG OVERSOLD
            # ---------------------------------------------
            if rsi <= 30:
                strength = min(
                    1.0,
                    max(
                        0.0,
                        (
                            50.0 - rsi
                        )
                        / 20.0,
                    ),
                )
                bullish_strength += (
                    strength
                    * self.RSI_WEIGHT
                )
                if strength >= (
                    self.MIN_INDICATOR_STRENGTH
                ):
                    bullish_confirmations += 1
                reasons.append(
                    (
                        "RSI: oversold "
                        f"({rsi:.1f})"
                    )
                )
            # ---------------------------------------------
            # MODERATE OVERSOLD
            # ---------------------------------------------
            elif rsi < 40:
                strength = (
                    40.0 - rsi
                ) / 20.0
                strength = min(
                    0.75,
                    max(
                        0.0,
                        strength,
                    ),
                )
                bullish_strength += (
                    strength
                    * self.RSI_WEIGHT
                )
                if strength >= (
                    self.MIN_INDICATOR_STRENGTH
                ):
                    bullish_confirmations += 1
                reasons.append(
                    (
                        "RSI: bullish zone "
                        f"({rsi:.1f})"
                    )
                )
            # ---------------------------------------------
            # STRONG OVERBOUGHT
            # ---------------------------------------------
            elif rsi >= 70:
                strength = min(
                    1.0,
                    max(
                        0.0,
                        (
                            rsi - 50.0
                        )
                        / 20.0,
                    ),
                )
                bearish_strength += (
                    strength
                    * self.RSI_WEIGHT
                )
                if strength >= (
                    self.MIN_INDICATOR_STRENGTH
                ):
                    bearish_confirmations += 1
                reasons.append(
                    (
                        "RSI: overbought "
                        f"({rsi:.1f})"
                    )
                )
            # ---------------------------------------------
            # MODERATE OVERBOUGHT
            # ---------------------------------------------
            elif rsi > 60:
                strength = (
                    rsi - 60.0
                ) / 20.0
                strength = min(
                    0.75,
                    max(
                        0.0,
                        strength,
                    ),
                )
                bearish_strength += (
                    strength
                    * self.RSI_WEIGHT
                )
                if strength >= (
                    self.MIN_INDICATOR_STRENGTH
                ):
                    bearish_confirmations += 1
                reasons.append(
                    (
                        "RSI: bearish zone "
                        f"({rsi:.1f})"
                    )
                )
            # ---------------------------------------------
            # NEUTRAL
            # ---------------------------------------------
            else:
                reasons.append(
                    (
                        "RSI: neutral "
                        f"({rsi:.1f})"
                    )
                )
        # =================================================
        # MACD
        # =================================================
        if (
            indicators.macd is not None
            and indicators.macd_signal is not None
        ):
            checks += 1
            macd = float(
                indicators.macd
            )
            macd_signal = float(
                indicators.macd_signal
            )
            difference = (
                macd
                - macd_signal
            )
            # ---------------------------------------------
            # BULLISH
            # ---------------------------------------------
            if difference > 0:
                # Нормализация силы.
                #
                # MACD может иметь очень маленькие значения,
                # поэтому используем относительное отношение
                # к величине самого MACD.
                denominator = max(
                    abs(macd_signal),
                    1e-8,
                )
                relative = abs(
                    difference
                ) / denominator
                strength = min(
                    1.0,
                    max(
                        0.20,
                        relative,
                    ),
                )
                bullish_strength += (
                    strength
                    * self.MACD_WEIGHT
                )
                if strength >= (
                    self.MIN_INDICATOR_STRENGTH
                ):
                    bullish_confirmations += 1
                reasons.append(
                    (
                        "MACD: bullish "
                        f"({strength * 100:.0f}%)"
                    )
                )
            # ---------------------------------------------
            # BEARISH
            # ---------------------------------------------
            elif difference < 0:
                denominator = max(
                    abs(macd_signal),
                    1e-8,
                )
                relative = abs(
                    difference
                ) / denominator
                strength = min(
                    1.0,
                    max(
                        0.20,
                        relative,
                    ),
                )
                bearish_strength += (
                    strength
                    * self.MACD_WEIGHT
                )
                if strength >= (
                    self.MIN_INDICATOR_STRENGTH
                ):
                    bearish_confirmations += 1
                reasons.append(
                    (
                        "MACD: bearish "
                        f"({strength * 100:.0f}%)"
                    )
                )
            else:
                reasons.append(
                    "MACD: neutral"
                )
        # =================================================
        # BOLLINGER BANDS
        # =================================================
        if (
            indicators.bollinger_upper
            is not None
            and indicators.bollinger_lower
            is not None
        ):
            checks += 1
            price = float(
                indicators.price
            )
            upper = float(
                indicators.bollinger_upper
            )
            lower = float(
                indicators.bollinger_lower
            )
            band_width = (
                upper - lower
            )
            # Защита от деления на ноль.
            if band_width <= 0:
                reasons.append(
                    "Bollinger: neutral"
                )
            # ---------------------------------------------
            # BELOW LOWER BAND
            # ---------------------------------------------
            elif price <= lower:
                distance = (
                    lower - price
                )
                strength = min(
                    1.0,
                    max(
                        0.25,
                        distance
                        / band_width
                        * 4.0,
                    ),
                )
                bullish_strength += (
                    strength
                    * self.BOLLINGER_WEIGHT
                )
                if strength >= (
                    self.MIN_INDICATOR_STRENGTH
                ):
                    bullish_confirmations += 1
                reasons.append(
                    (
                        "Bollinger: lower band "
                        f"({strength * 100:.0f}%)"
                    )
                )
            # ---------------------------------------------
            # ABOVE UPPER BAND
            # ---------------------------------------------
            elif price >= upper:
                distance = (
                    price - upper
                )
                strength = min(
                    1.0,
                    max(
                        0.25,
                        distance
                        / band_width
                        * 4.0,
                    ),
                )
                bearish_strength += (
                    strength
                    * self.BOLLINGER_WEIGHT
                )
                if strength >= (
                    self.MIN_INDICATOR_STRENGTH
                ):
                    bearish_confirmations += 1
                reasons.append(
                    (
                        "Bollinger: upper band "
                        f"({strength * 100:.0f}%)"
                    )
                )
            # ---------------------------------------------
            # INSIDE BANDS
            # ---------------------------------------------
            else:
                # Позиция цены внутри диапазона.
                position = (
                    price - lower
                ) / band_width
                # Нижняя половина диапазона
                # слегка поддерживает UP.
                if position < 0.40:
                    strength = min(
                        0.35,
                        max(
                            0.0,
                            (
                                0.50
                                - position
                            )
                            * 0.7,
                        ),
                    )
                    if strength > 0:
                        bullish_strength += (
                            strength
                            * self.BOLLINGER_WEIGHT
                        )
                        if strength >= (
                            self.MIN_INDICATOR_STRENGTH
                        ):
                            bullish_confirmations += 1
                        reasons.append(
                            (
                                "Bollinger: "
                                "lower-side bias"
                            )
                        )
                    else:
                        reasons.append(
                            "Bollinger: neutral"
                        )
                # Верхняя половина диапазона
                # слегка поддерживает DOWN.
                elif position > 0.60:
                    strength = min(
                        0.35,
                        max(
                            0.0,
                            (
                                position
                                - 0.50
                            )
                            * 0.7,
                        ),
                    )
                    if strength > 0:
                        bearish_strength += (
                            strength
                            * self.BOLLINGER_WEIGHT
                        )
                        if strength >= (
                            self.MIN_INDICATOR_STRENGTH
                        ):
                            bearish_confirmations += 1
                        reasons.append(
                            (
                                "Bollinger: "
                                "upper-side bias"
                            )
                        )
                    else:
                        reasons.append(
                            "Bollinger: neutral"
                        )
                else:
                    reasons.append(
                        "Bollinger: neutral"
                    )
        # =================================================
        # NO CHECKS
        # =================================================
        if checks == 0:
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
        # TOTAL STRENGTH
        # =================================================
        total_strength = (
            bullish_strength
            + bearish_strength
        )
        if total_strength <= 0:
            return AnalysisResult(
                direction=None,
                score=0.0,
                reasons=[
                    *reasons,
                    "Нет направленного "
                    "подтверждения.",
                ],
                confirmations=0,
                total_checks=checks,
            )
        # =================================================
        # DIRECTION
        # =================================================
        if (
            bullish_strength
            > bearish_strength
        ):
            direction = Direction.UP
            dominant_strength = (
                bullish_strength
            )
            opposing_strength = (
                bearish_strength
            )
            confirmations = (
                bullish_confirmations
            )
        elif (
            bearish_strength
            > bullish_strength
        ):
            direction = Direction.DOWN
            dominant_strength = (
                bearish_strength
            )
            opposing_strength = (
                bullish_strength
            )
            confirmations = (
                bearish_confirmations
            )
        else:
            return AnalysisResult(
                direction=None,
                score=0.0,
                reasons=[
                    *reasons,
                    "Индикаторы дают "
                    "конфликтующий сигнал.",
                ],
                confirmations=0,
                total_checks=checks,
            )
        # =================================================
        # DIRECTION ADVANTAGE
        # =================================================
        direction_advantage = (
            dominant_strength
            - opposing_strength
        )
        normalized_advantage = (
            direction_advantage
            / max(
                dominant_strength,
                1e-8,
            )
        )
        # =================================================
        # TOO MUCH CONFLICT
        # =================================================
        if (
            normalized_advantage
            < self.MIN_DIRECTION_ADVANTAGE
        ):
            return AnalysisResult(
                direction=None,
                score=0.0,
                reasons=[
                    *reasons,
                    (
                        "Недостаточное "
                        "преимущество направления."
                    ),
                ],
                confirmations=0,
                total_checks=checks,
            )
        # =================================================
        # SCORE
        # =================================================
        #
        # Сила доминирующего направления.
        #
        maximum_possible = (
            self.EMA_WEIGHT
            + self.RSI_WEIGHT
            + self.MACD_WEIGHT
            + self.BOLLINGER_WEIGHT
        )
        strength_ratio = (
            dominant_strength
            / maximum_possible
        )
        strength_score = (
            strength_ratio
            * 100.0
        )
        #
        # Бонус за отсутствие сильного конфликта.
        #
        agreement_score = (
            normalized_advantage
            * 20.0
        )
        #
        # Финальный score.
        #
        score = min(
            100.0,
            max(
                0.0,
                strength_score
                + agreement_score,
            ),
        )
        # =================================================
        # FINAL REASONS
        # =================================================
        reasons.append(
            (
                f"Итоговое направление: "
                f"{'UP' if direction == Direction.UP else 'DOWN'}"
            )
        )
        reasons.append(
            (
                f"Сила направления: "
                f"{dominant_strength:.2f}"
            )
        )
        reasons.append(
            (
                f"Конфликтующая сила: "
                f"{opposing_strength:.2f}"
            )
        )
        reasons.append(
            (
                f"Преимущество направления: "
                f"{normalized_advantage * 100:.1f}%"
            )
        )
        reasons.append(
            (
                f"Итоговый score: "
                f"{score:.1f}%"
            )
        )
        # =================================================
        # RETURN
        # =================================================
        return AnalysisResult(
            direction=direction,
            score=score,
            reasons=reasons,
            confirmations=confirmations,
            total_checks=checks,
        )
# =========================================================
# GLOBAL ENGINE
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
