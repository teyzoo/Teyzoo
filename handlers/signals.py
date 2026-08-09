from aiogram import Router, F
from aiogram.types import Message

from database import (
    get_signal_statistics,
)

from market import (
    market_client,
    MarketDataError,
)

from predictor import predictor

from filters import passes_filter


router = Router()


@router.message(
    F.text == "📊 Получить сигнал"
)
async def get_signal(
    message: Message,
):

    await message.answer(
        "🔎 <b>АНАЛИЗ РЫНКА</b>\n\n"
        "Проверяю доступные данные...\n"
        "⏳ Пожалуйста, подождите.",
        parse_mode="HTML",
    )

    try:

        candles = (
            await market_client.get_candles(
                "EUR/USD",
                timeframe="1m",
                limit=200,
            )
        )

    except MarketDataError:

        await message.answer(
            "⛔ <b>NO SIGNAL</b>\n\n"
            "Актуальные рыночные данные "
            "сейчас недоступны.\n\n"
            "❌ Бот не создаёт сигнал "
            "на основе выдуманных данных.",
            parse_mode="HTML",
        )

        return

    prediction = predictor.predict(
        candles
    )

    if not passes_filter(
        prediction
    ):

        await message.answer(
            "⛔ <b>NO SIGNAL</b>\n\n"
            "Подходящая сделка не прошла "
            "строгую систему фильтрации.",
            parse_mode="HTML",
        )

        return

    await message.answer(
        "🚨 <b>SIGNAL</b>\n\n"
        "💱 Пара: EUR/USD\n"
        f"🎯 Quality score: "
        f"{prediction.score:.1f}%\n\n"
        "⚠️ Историческая вероятность "
        "будет показана только после "
        "достаточного количества "
        "результатов backtest.",
        parse_mode="HTML",
    )


@router.message(
    F.text == "📈 Статистика"
)
async def statistics(
    message: Message,
):

    stats = (
        await get_signal_statistics()
    )

    await message.answer(
        "📈 <b>СТАТИСТИКА СИГНАЛОВ</b>\n\n"
        f"📊 Всего: "
        f"<b>{stats['total']}</b>\n"
        f"✅ Побед: "
        f"<b>{stats['wins']}</b>\n"
        f"❌ Поражений: "
        f"<b>{stats['losses']}</b>\n"
        f"🎯 Win Rate: "
        f"<b>{stats['win_rate']:.2f}%</b>\n\n"
        "Статистика строится только "
        "по сохранённым результатам.",
        parse_mode="HTML",
    )
