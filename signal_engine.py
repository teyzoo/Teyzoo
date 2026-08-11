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
    """
    Результат анализа одного таймфрейма.
    direction:
        UP / DOWN / None
    score:
        Сила доминирующего направления
        в диапазоне 0-100.
    reasons:
        Подробные причины сигнала.
    confirmations:
        Количество индикаторов, которые подтвердили
        доминирующее направление.
    total_checks:
        Количество реально рассчитанных индикаторов.
    """
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
    Основной движок анализа одного таймфрейма.
    Используемые индикаторы:
        EMA       = 25%
        RSI       = 25%
        MACD      = 30%
        Bollinger = 20%
    Максимальный score:
        100%
    ВАЖНО:
    Нейтральный индикатор НЕ считается отрицательным.
    Например:
        EMA       -> UP       +25
        RSI       -> neutral   0
        MACD      -> UP       +30
        Bollinger -> neutral   0
    Результат:
        UP = 55%
    а не:
        55 / 4 = 13.75%
    То есть score показывает фактическую сумму
    направленных подтверждений.
    =====================================================
    RSI:
    RSI не используется как простой:
        RSI <= 35 -> UP
        RSI >= 65 -> DOWN
    потому что это контртрендовая интерпретация.
    Например:
        сильный нисходящий тренд
        RSI = 25
    не обязательно означает немедленный UP.
    Поэтому RSI работает через зоны:
        50-65 -> bullish
        35-50 -> bearish
    Экстремальные значения:
        <= 30 -> сильный bullish reversal context
        >= 70 -> сильный bearish reversal context
    Но экстремум получает дополнительное описание
    и не ломает EMA/MACD-логику.
    """
    # =====================================================
    # WEIGHTS
    # =====================================================
    EMA_WEIGHT = 25.0
    RSI_WEIGHT = 25.0
    MACD_WEIGHT = 30.0
    BOLLINGER_WEIGHT = 20.0
    # =====================================================
    # RSI ZONES
    # =====================================================
    RSI_OVERSOLD = 30.0
    RSI_BULLISH = 50.0
    RSI_BEARISH = 50.0
    RSI_OVERBOUGHT = 70.0
    # =====================================================
    # BOLLINGER
    # =====================================================
    # Используем небольшую tolerance-зону,
    # чтобы цена, находящаяся буквально рядом
    # с полосой, не считалась нейтральной
    # из-за микроскопического движения.
    BOLLINGER_TOLERANCE = 0.001
    # =====================================================
    # MINIMUM CANDLES
    # =====================================================
    MIN_CANDLES = 50
    # =====================================================
    # SCORE EPSILON
    # =====================================================
    SCORE_EPSILON = 0.000001
    # =====================================================
    # ANALYZE
    # =====================================================
    def analyze(
        self,
        candles: list[Candle],
    ) -> AnalysisResult:
        """
        Анализирует один набор свечей.
        Ожидается:
            candles = свечи одного таймфрейма.
        Возвращает:
            AnalysisResult
        """
        # =================================================
        # VALIDATE CANDLES
        # =================================================
        if len(candles) < self.MIN_CANDLES:
            return AnalysisResult(
                direction=None,
                score=0.0,
                reasons=[
                    (
                        "Недостаточно свечей: "
                        f"{len(candles)}/"
                        f"{self.MIN_CANDLES}."
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
        # =================================================
        # CONFIRMATIONS
        # =================================================
        bullish_confirmations = 0
        bearish_confirmations = 0
        # =================================================
        # REASONS
        # =================================================
        reasons: list[str] = []
        # =================================================
        # CHECKS
        # =================================================
        total_checks = 0
        # =================================================
        # PRICE VALIDATION
        # =================================================
        try:
            price = float(
                indicators.price
            )
        except Exception:
            price = 0.0
        if price <= 0:
            return AnalysisResult(
                direction=None,
                score=0.0,
                reasons=[
                    "Некорректная текущая цена."
                ],
                confirmations=0,
                total_checks=0,
            )
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
                        f"+{self.EMA_WEIGHT:.0f}% "
                        f"(fast={ema_fast:.6f}, "
                        f"slow={ema_slow:.6f})"
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
                        f"+{self.EMA_WEIGHT:.0f}% "
                        f"(fast={ema_fast:.6f}, "
                        f"slow={ema_slow:.6f})"
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
            # EXTREME OVERSOLD
            # -------------------------------------------------
            if rsi <= self.RSI_OVERSOLD:
                bullish_score += (
                    self.RSI_WEIGHT
                )
                bullish_confirmations += 1
                reasons.append(
                    (
                        "RSI: extreme oversold "
                        f"({rsi:.1f}) "
                        f"+{self.RSI_WEIGHT:.0f}% "
                        "(bullish reversal)"
                    )
                )
            # -------------------------------------------------
            # BULLISH
            # -------------------------------------------------
            elif rsi > self.RSI_BULLISH:
                bullish_score += (
                    self.RSI_WEIGHT
                )
                bullish_confirmations += 1
                reasons.append(
                    (
                        "RSI: bullish "
                        f"({rsi:.1f}) "
                        f"+{self.RSI_WEIGHT:.0f}%"
                    )
                )
            # -------------------------------------------------
            # EXTREME OVERBOUGHT
            # -------------------------------------------------
            elif rsi >= self.RSI_OVERBOUGHT:
                bearish_score += (
                    self.RSI_WEIGHT
                )
                bearish_confirmations += 1
                reasons.append(
                    (
                        "RSI: extreme overbought "
                        f"({rsi:.1f}) "
                        f"+{self.RSI_WEIGHT:.0f}% "
                        "(bearish reversal)"
                    )
                )
            # -------------------------------------------------
            # BEARISH
            # -------------------------------------------------
            elif rsi < self.RSI_BEARISH:
                bearish_score += (
                    self.RSI_WEIGHT
                )
                bearish_confirmations += 1
                reasons.append(
                    (
                        "RSI: bearish "
                        f"({rsi:.1f}) "
                        f"+{self.RSI_WEIGHT:.0f}%"
                    )
                )
            # -------------------------------------------------
            # NEUTRAL
            # -------------------------------------------------
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
            if macd > macd_signal:
                bullish_score += (
                    self.MACD_WEIGHT
                )
                bullish_confirmations += 1
                reasons.append(
                    (
                        "MACD: bullish "
                        f"+{self.MACD_WEIGHT:.0f}% "
                        f"(macd={macd:.6f}, "
                        f"signal={macd_signal:.6f})"
                    )
                )
            elif macd < macd_signal:
                bearish_score += (
                    self.MACD_WEIGHT
                )
                bearish_confirmations += 1
                reasons.append(
                    (
                        "MACD: bearish "
                        f"+{self.MACD_WEIGHT:.0f}% "
                        f"(macd={macd:.6f}, "
                        f"signal={macd_signal:.6f})"
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
            upper = float(
                indicators.bollinger_upper
            )
            lower = float(
                indicators.bollinger_lower
            )
            # -------------------------------------------------
            # INVALID BANDS
            # -------------------------------------------------
            if upper <= lower:
                reasons.append(
                    "Bollinger: invalid bands"
                )
            else:
                band_width = (
                    upper - lower
                )
                tolerance = (
                    band_width
                    * self.BOLLINGER_TOLERANCE
                )
                # -------------------------------------------------
                # LOWER BAND
                # -------------------------------------------------
                if price <= (
                    lower + tolerance
                ):
                    bullish_score += (
                        self.BOLLINGER_WEIGHT
                    )
                    bullish_confirmations += 1
                    reasons.append(
                        (
                            "Bollinger: near/below "
                            "lower band "
                            f"+{self.BOLLINGER_WEIGHT:.0f}% "
                            f"(price={price:.6f})"
                        )
                    )
                # -------------------------------------------------
                # UPPER BAND
                # -------------------------------------------------
                elif price >= (
                    upper - tolerance
                ):
                    bearish_score += (
                        self.BOLLINGER_WEIGHT
                    )
                    bearish_confirmations += 1
                    reasons.append(
                        (
                            "Bollinger: near/above "
                            "upper band "
                            f"+{self.BOLLINGER_WEIGHT:.0f}% "
                            f"(price={price:.6f})"
                        )
                    )
                # -------------------------------------------------
                # NEUTRAL
                # -------------------------------------------------
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
        # TOTAL SCORE
        # =================================================
        total_direction_score = (
            bullish_score
            + bearish_score
        )
        # =================================================
        # NO DIRECTION
        # =================================================
        if (
            total_direction_score
            <= self.SCORE_EPSILON
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
        # CONFLICT
        # =================================================
        if (
            abs(
                bullish_score
                - bearish_score
            )
            <= self.SCORE_EPSILON
        ):
            return AnalysisResult(
                direction=None,
                score=0.0,
                reasons=[
                    *reasons,
                    (
                        "Индикаторы дают "
                        "равный конфликтующий сигнал."
                    ),
                    (
                        f"Bullish score: "
                        f"{bullish_score:.1f}%"
                    ),
                    (
                        f"Bearish score: "
                        f"{bearish_score:.1f}%"
                    ),
                ],
                confirmations=0,
                total_checks=total_checks,
            )
        # =================================================
        # DETERMINE DIRECTION
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
        else:
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
        # =================================================
        # DIRECTION STRENGTH
        # =================================================
        direction_strength = (
            dominant_score / 100.0
        )
        # =================================================
        # ADVANTAGE
        # =================================================
        if total_direction_score > 0:
            advantage = (
                dominant_score
                / total_direction_score
                * 100.0
            )
        else:
            advantage = 0.0
        # =================================================
        # CONFIRMATION RATIO
        # =================================================
        confirmation_ratio = (
            confirmations
            / total_checks
            * 100.0
            if total_checks > 0
            else 0.0
        )
        # =================================================
        # DIRECTION TEXT
        # =================================================
        if direction == Direction.UP:
            direction_text = "UP"
        else:
            direction_text = "DOWN"
        # =================================================
        # FINAL REASONS
        # =================================================
        reasons.append(
            (
                "Итоговое направление: "
                f"{direction_text}"
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
                "Подтверждения: "
                f"{confirmations}/"
                f"{total_checks} "
                f"({confirmation_ratio:.1f}%)"
            )
        )
        reasons.append(
            (
                "Bullish score: "
                f"{bullish_score:.1f}%"
            )
        )
        reasons.append(
            (
                "Bearish score: "
                f"{bearish_score:.1f}%"
            )
        )
        reasons.append(
            (
                "Итоговый score: "
                f"{dominant_score:.1f}%"
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
                    dominant_score,
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
