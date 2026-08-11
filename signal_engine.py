from __future__ import annotations
from dataclasses import dataclass
from indicators import calculate_indicators
from market import Candle
from models import Direction
# =========================================================
# DATA MODEL
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
    Движок анализа одного таймфрейма.
    Индикаторы:
        EMA       -> тренд
        RSI       -> импульс / перекупленность / перепроданность
        MACD      -> импульс и направление
        Bollinger -> положение цены внутри диапазона
    В отличие от старой версии:
        - нейтральный индикатор не даёт штраф;
        - несколько согласованных индикаторов дают бонус;
        - конфликтующие индикаторы уменьшают score;
        - RSI работает не только на 35/65;
        - Bollinger учитывает положение цены внутри диапазона;
        - score может превышать 55%, когда несколько
          индикаторов реально подтверждают одно направление.
    ВАЖНО:
        score != вероятность WIN.
    Это внутренняя сила сигнала.
    Реальный WINRATE необходимо считать отдельно
    по историческим результатам.
    """
    # =====================================================
    # BASE WEIGHTS
    # =====================================================
    EMA_WEIGHT = 25.0
    RSI_WEIGHT = 25.0
    MACD_WEIGHT = 30.0
    BOLLINGER_WEIGHT = 20.0
    # =====================================================
    # RSI
    # =====================================================
    RSI_STRONG_OVERSOLD = 30.0
    RSI_OVERSOLD = 40.0
    RSI_STRONG_OVERBOUGHT = 70.0
    RSI_OVERBOUGHT = 60.0
    # =====================================================
    # BOLLINGER
    # =====================================================
    BOLLINGER_EXTREME_ZONE = 0.15
    BOLLINGER_STRONG_ZONE = 0.30
    BOLLINGER_WEAK_ZONE = 0.50
    # =====================================================
    # BONUSES
    # =====================================================
    # 2 индикатора в одном направлении
    AGREEMENT_2_BONUS = 5.0
    # 3 индикатора
    AGREEMENT_3_BONUS = 10.0
    # 4 индикатора
    AGREEMENT_4_BONUS = 15.0
    # =====================================================
    # CONFLICT PENALTY
    # =====================================================
    CONFLICT_PENALTY = 5.0
    # =====================================================
    # MINIMUM CANDLES
    # =====================================================
    MIN_CANDLES = 50
    # =====================================================
    # HELPERS
    # =====================================================
    @staticmethod
    def _clamp(
        value: float,
        minimum: float = 0.0,
        maximum: float = 100.0,
    ) -> float:
        return max(
            minimum,
            min(
                maximum,
                float(value),
            ),
        )
    # =====================================================
    # ANALYZE
    # =====================================================
    def analyze(
        self,
        candles: list[Candle],
    ) -> AnalysisResult:
        # =================================================
        # CANDLE VALIDATION
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
        # CALCULATE INDICATORS
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
        # SCORES
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
            ema_fast = float(
                indicators.ema_fast
            )
            ema_slow = float(
                indicators.ema_slow
            )
            if ema_fast > ema_slow:
                bullish_score += (
                    self.EMA_WEIGHT
                )
                bullish_confirmations += 1
                reasons.append(
                    (
                        "EMA: bullish "
                        f"({self.EMA_WEIGHT:.0f}%)"
                    )
                )
            elif ema_fast < ema_slow:
                bearish_score += (
                    self.EMA_WEIGHT
                )
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
            # -------------------------------------------------
            # STRONG OVERSOLD
            # -------------------------------------------------
            if rsi <= self.RSI_STRONG_OVERSOLD:
                bullish_score += (
                    self.RSI_WEIGHT
                )
                bullish_confirmations += 1
                reasons.append(
                    (
                        "RSI: strong oversold "
                        f"({rsi:.1f}) "
                        f"+{self.RSI_WEIGHT:.0f}%"
                    )
                )
            # -------------------------------------------------
            # OVERSOLD
            # -------------------------------------------------
            elif rsi <= self.RSI_OVERSOLD:
                partial = (
                    self.RSI_WEIGHT
                    * 0.70
                )
                bullish_score += partial
                bullish_confirmations += 1
                reasons.append(
                    (
                        "RSI: oversold "
                        f"({rsi:.1f}) "
                        f"+{partial:.1f}%"
                    )
                )
            # -------------------------------------------------
            # STRONG OVERBOUGHT
            # -------------------------------------------------
            elif rsi >= self.RSI_STRONG_OVERBOUGHT:
                bearish_score += (
                    self.RSI_WEIGHT
                )
                bearish_confirmations += 1
                reasons.append(
                    (
                        "RSI: strong overbought "
                        f"({rsi:.1f}) "
                        f"+{self.RSI_WEIGHT:.0f}%"
                    )
                )
            # -------------------------------------------------
            # OVERBOUGHT
            # -------------------------------------------------
            elif rsi >= self.RSI_OVERBOUGHT:
                partial = (
                    self.RSI_WEIGHT
                    * 0.70
                )
                bearish_score += partial
                bearish_confirmations += 1
                reasons.append(
                    (
                        "RSI: overbought "
                        f"({rsi:.1f}) "
                        f"+{partial:.1f}%"
                    )
                )
            # -------------------------------------------------
            # BULLISH MOMENTUM
            # -------------------------------------------------
            elif 50.0 <= rsi < 60.0:
                partial = (
                    self.RSI_WEIGHT
                    * 0.45
                )
                bullish_score += partial
                bullish_confirmations += 1
                reasons.append(
                    (
                        "RSI: bullish momentum "
                        f"({rsi:.1f}) "
                        f"+{partial:.1f}%"
                    )
                )
            # -------------------------------------------------
            # BEARISH MOMENTUM
            # -------------------------------------------------
            elif 40.0 < rsi < 50.0:
                partial = (
                    self.RSI_WEIGHT
                    * 0.45
                )
                bearish_score += partial
                bearish_confirmations += 1
                reasons.append(
                    (
                        "RSI: bearish momentum "
                        f"({rsi:.1f}) "
                        f"+{partial:.1f}%"
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
            macd = float(
                indicators.macd
            )
            macd_signal = float(
                indicators.macd_signal
            )
            difference = (
                macd - macd_signal
            )
            # -------------------------------------------------
            # BULLISH
            # -------------------------------------------------
            if difference > 0:
                bullish_score += (
                    self.MACD_WEIGHT
                )
                bullish_confirmations += 1
                reasons.append(
                    (
                        "MACD: bullish "
                        f"({self.MACD_WEIGHT:.0f}%)"
                    )
                )
            # -------------------------------------------------
            # BEARISH
            # -------------------------------------------------
            elif difference < 0:
                bearish_score += (
                    self.MACD_WEIGHT
                )
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
            and indicators.price is not None
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
            band_width = (
                upper - lower
            )
            # -------------------------------------------------
            # INVALID BAND
            # -------------------------------------------------
            if band_width <= 0:
                reasons.append(
                    "Bollinger: invalid range"
                )
            else:
                position = (
                    price - lower
                ) / band_width
                position = self._clamp(
                    position,
                    0.0,
                    1.0,
                )
                # ---------------------------------------------
                # EXTREME LOWER
                # ---------------------------------------------
                if (
                    position
                    <= self.BOLLINGER_EXTREME_ZONE
                ):
                    bullish_score += (
                        self.BOLLINGER_WEIGHT
                    )
                    bullish_confirmations += 1
                    reasons.append(
                        (
                            "Bollinger: near lower band "
                            f"({self.BOLLINGER_WEIGHT:.0f}%)"
                        )
                    )
                # ---------------------------------------------
                # LOWER ZONE
                # ---------------------------------------------
                elif (
                    position
                    <= self.BOLLINGER_STRONG_ZONE
                ):
                    partial = (
                        self.BOLLINGER_WEIGHT
                        * 0.70
                    )
                    bullish_score += partial
                    bullish_confirmations += 1
                    reasons.append(
                        (
                            "Bollinger: lower zone "
                            f"+{partial:.1f}%"
                        )
                    )
                # ---------------------------------------------
                # UPPER EXTREME
                # ---------------------------------------------
                elif (
                    position
                    >= 1.0
                    - self.BOLLINGER_EXTREME_ZONE
                ):
                    bearish_score += (
                        self.BOLLINGER_WEIGHT
                    )
                    bearish_confirmations += 1
                    reasons.append(
                        (
                            "Bollinger: near upper band "
                            f"({self.BOLLINGER_WEIGHT:.0f}%)"
                        )
                    )
                # ---------------------------------------------
                # UPPER ZONE
                # ---------------------------------------------
                elif (
                    position
                    >= 1.0
                    - self.BOLLINGER_STRONG_ZONE
                ):
                    partial = (
                        self.BOLLINGER_WEIGHT
                        * 0.70
                    )
                    bearish_score += partial
                    bearish_confirmations += 1
                    reasons.append(
                        (
                            "Bollinger: upper zone "
                            f"+{partial:.1f}%"
                        )
                    )
                # ---------------------------------------------
                # MIDDLE
                # ---------------------------------------------
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
        # NO DIRECTION
        # =================================================
        if (
            bullish_score <= 0.0
            and bearish_score <= 0.0
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
        # DIRECTION
        # =================================================
        if bullish_score > bearish_score:
            direction = Direction.UP
            dominant_score = (
                bullish_score
            )
            conflict_score = (
                bearish_score
            )
            confirmations = (
                bullish_confirmations
            )
        elif bearish_score > bullish_score:
            direction = Direction.DOWN
            dominant_score = (
                bearish_score
            )
            conflict_score = (
                bullish_score
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
                    (
                        "Индикаторы дают "
                        "конфликтующий сигнал."
                    ),
                ],
                confirmations=0,
                total_checks=total_checks,
            )
        # =================================================
        # AGREEMENT BONUS
        # =================================================
        bonus = 0.0
        if confirmations >= 4:
            bonus += (
                self.AGREEMENT_4_BONUS
            )
            reasons.append(
                (
                    "Согласие 4 индикаторов: "
                    f"+{self.AGREEMENT_4_BONUS:.0f}%"
                )
            )
        elif confirmations >= 3:
            bonus += (
                self.AGREEMENT_3_BONUS
            )
            reasons.append(
                (
                    "Согласие 3 индикаторов: "
                    f"+{self.AGREEMENT_3_BONUS:.0f}%"
                )
            )
        elif confirmations >= 2:
            bonus += (
                self.AGREEMENT_2_BONUS
            )
            reasons.append(
                (
                    "Согласие 2 индикаторов: "
                    f"+{self.AGREEMENT_2_BONUS:.0f}%"
                )
            )
        # =================================================
        # CONFLICT PENALTY
        # =================================================
        if conflict_score > 0:
            penalty = (
                min(
                    self.CONFLICT_PENALTY,
                    conflict_score * 0.20,
                )
            )
            dominant_score -= penalty
            reasons.append(
                (
                    "Конфликт индикаторов: "
                    f"-{penalty:.1f}%"
                )
            )
        # =================================================
        # FINAL SCORE
        # =================================================
        score = (
            dominant_score
            + bonus
        )
        score = self._clamp(
            score,
            0.0,
            100.0,
        )
        # =================================================
        # ADVANTAGE
        # =================================================
        total_direction_score = (
            bullish_score
            + bearish_score
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
        # DIRECTION STRENGTH
        # =================================================
        direction_strength = (
            dominant_score
            / 100.0
        )
        # =================================================
        # FINAL REASONS
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
                "Подтверждений: "
                f"{confirmations}/{total_checks}"
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
            score=score,
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
