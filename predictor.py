from models import Direction, MarketCandle


class PredictionResult:

    def __init__(
        self,
        direction: Direction | None,
        score: float,
        reasons: list[str],
    ):
        self.direction = direction
        self.score = score
        self.reasons = reasons


class Predictor:

    def predict(
        self,
        candles: list[MarketCandle],
    ) -> PredictionResult:

        """
        Здесь будет реальная модель прогнозирования.

        Пока данных недостаточно, поэтому
        намеренно возвращаем отсутствие сигнала.

        Это лучше, чем генерировать
        случайные CALL/PUT.
        """

        return PredictionResult(
            direction=None,
            score=0,
            reasons=[
                "Недостаточно данных для подтверждённого сигнала."
            ],
        )


predictor = Predictor()
