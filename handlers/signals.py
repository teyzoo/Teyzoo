from aiogram import Router, F
from aiogram.types import Message

from config import TIMEZONE
from market import market_client, MarketDataError
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
        "🔎 Анализирую рынок...\n\n"
        "⏳ Проверяю доступные данные."
    )

    try:
        candles = await market_client.get_candles(
            "EUR/USD",
            limit=200,
        )

    except MarketDataError:
        await message.answer(
            "⛔ <b>NO SIGNAL</b>\n\n"
            "Источник рыночных данных пока "
            "не подключён.\n\n"
            "Бот не будет выдавать выдуманный "
            "прогноз без реальных данных.",
            parse_mode="HTML",
        )
        return

    prediction = predictor.predict(
        candles
    )

    if not passes_filter(prediction):
        await message.answer(
            "⛔ <b>NO SIGNAL</b>\n\n"
            "Подходящей сделки с достаточной "
            "уверенностью не найдено.",
            parse_mode="HTML",
        )
        return

    await message.answer(
        "🚨 <b>SIGNAL</b>\n\n"
        "💱 Пара: EUR/USD\n"
        f"🎯 Оценка: {prediction.score:.1f}%\n\n"
        "⚠️ Это статистический прогноз, "
        "а не гарантия результата.",
        parse_mode="HTML",
    )
