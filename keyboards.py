from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💸 Купить USDT")],
        [KeyboardButton(text="💵 Продать USDT")],
        [KeyboardButton(text="📊 Курс покупки / продажи")],
    ],
    resize_keyboard=True
)
