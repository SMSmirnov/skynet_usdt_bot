import asyncio
import re

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message

from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from config import settings
from keyboards import main_kb
from texts import (
    START_TEXT,
    BUY_ASK_AMOUNT_TEXT,
    BUY_ASK_CONTACT_TEXT,
    BUY_FINISH_TEXT,
    SELL_ASK_AMOUNT_TEXT,
    SELL_ASK_CONTACT_TEXT,
    SELL_FINISH_TEXT,
)


# ---------- СТЕЙТЫ ДЛЯ СДЕЛОК ----------

class DealStates(StatesGroup):
    buy_amount = State()
    buy_contact = State()
    sell_amount = State()
    sell_contact = State()


# Кнопки главного меню (чтобы отличить их от обычного текста)
MAIN_MENU_BUTTONS = {
    "💸 Купить USDT",
    "💵 Продать USDT",
    "📊 Курс покупки / продажи",
}

# ---------- ИНИЦИАЛИЗАЦИЯ БОТА ----------

bot = Bot(
    token=settings.bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()

print("✅ Настройки загружены:")
print(f"BOT_TOKEN начинается с: {settings.bot_token[:9]}")
print(f"ADMIN_CHAT_ID: {settings.admin_chat_id}")
print(f"RAPIRA_UID: {settings.rapira_uid}")
print("🔥 SKYNET USDT BOT запускается...")


# ---------- ХЕЛПЕР ОТПРАВКИ АДМИНУ ----------

async def notify_admin(text: str) -> None:
    try:
        await bot.send_message(chat_id=settings.admin_chat_id, text=text)
    except Exception as e:
        print(f"Ошибка отправки админу: {e}")


# ---------- /start ----------

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(START_TEXT, reply_markup=main_kb)


# ---------- ПОКУПКА USDT ----------

@dp.message(F.text == "💸 Купить USDT")
async def buy_start(message: Message, state: FSMContext):
    """Начало сценария покупки: показываем курс и спрашиваем сумму."""
    await state.clear()

    from rapira_api import fetch_usdt_rub_rate
    rates = await fetch_usdt_rub_rate()
    if not rates:
        await message.answer("⚠️ Не удалось получить курс. Попробуйте чуть позже.")
        return

    buy_rate = rates["buy_to_client"]  # курс, по которому клиент ПОКУПАЕТ USDT у нас

    # Используем текст из texts.py
    text = BUY_ASK_AMOUNT_TEXT.replace("Курс:", f"Курс: {buy_rate:.2f} ₽")

    await message.answer(text, reply_markup=None)
    await state.set_state(DealStates.buy_amount)



@dp.message(DealStates.buy_amount)
async def buy_amount(message: Message, state: FSMContext):
    text = message.text.strip()

    # нажали одну из кнопок меню вместо суммы
    if text in MAIN_MENU_BUTTONS:
        await state.clear()
        if text == "💸 Купить USDT":
            return await buy_start(message, state)
        if text == "💵 Продать USDT":
            return await sell_start(message, state)
        if text == "📊 Курс покупки / продажи":
            return await show_course(message, state)

    # --- парсим сумму ---
    clean = text.replace(" ", "")
    from rapira_api import fetch_usdt_rub_rate
    rates = await fetch_usdt_rub_rate()
    if not rates:
        await message.answer("⚠️ Не удалось получить курс. Попробуйте позже.")
        return

    buy_rate = rates["buy_to_client"]  # RUB за 1 USDT

    try:
        if clean.upper().endswith("USDT"):
            # сумма введена в USDT
            num = re.sub(r'(?i)USDT$', "", clean)
            usdt_amount = float(num.replace(",", "."))
            rub_amount = usdt_amount * buy_rate
            await message.answer(
                f"💡 Это примерно {rub_amount:.2f} ₽ за {usdt_amount:.6f} USDT."
            )
        else:
            # считаем, что сумма в рублях; допускаем: ₽, р, руб, руб., рублей
            m = re.match(
                r'^([\d.,]+)(?:₽|р\.?|руб\.?|рублей)?$',
                clean,
                flags=re.IGNORECASE,
            )
            if not m:
                raise ValueError("bad format")

            rub_amount = float(m.group(1).replace(" ", "").replace(",", "."))
            usdt_amount = rub_amount / buy_rate
            await message.answer(
                f"💡 Это примерно {usdt_amount:.6f} USDT за {rub_amount:.2f} ₽."
            )
    except ValueError:
        await message.answer(
            "❗ Пожалуйста, введите корректную сумму, например "
            "'100000', '100000 руб' или '150 USDT'."
        )
        return

    # сохраняем исходный ввод (строкой)
    await state.update_data(amount=text)
    await state.set_state(DealStates.buy_contact)
    await message.answer(BUY_ASK_CONTACT_TEXT)


@dp.message(DealStates.buy_contact)
async def buy_contact(message: Message, state: FSMContext):
    """Финальный шаг покупки: получили ФИО, шлём заявку админу."""
    data = await state.get_data()
    amount = data.get("amount", "—")
    fio = message.text.strip()

    user = message.from_user
    username = f"@{user.username}" if user.username else user.full_name

    admin_text = (
        "🆕 Новая заявка на ПОКУПКУ USDT\n\n"
        f"👤 Пользователь: {username} (id: {user.id})\n"
        "📍 Город: Москва\n"
        f"💰 Сумма: {amount}\n"
        f"📄 ФИО для пропуска: {fio}"
    )
    await notify_admin(admin_text)

    await message.answer(BUY_FINISH_TEXT, reply_markup=main_kb)
    await state.clear()


# ---------- ПРОДАЖА USDT ----------

@dp.message(F.text == "💵 Продать USDT")
async def sell_start(message: Message, state: FSMContext):
    """Начало сценария продажи: показываем курс и спрашиваем сумму."""
    await state.clear()

    from rapira_api import fetch_usdt_rub_rate
    rates = await fetch_usdt_rub_rate()
    if not rates:
        await message.answer("⚠️ Не удалось получить курс. Попробуйте чуть позже.")
        return

    sell_rate = rates["sell_from_client"]  # RUB за 1 USDT (когда клиент ПРОДАЁТ нам)

    await message.answer(
    SELL_ASK_AMOUNT_TEXT.replace("Курс:", f"Курс: {sell_rate:.2f} ₽")
)

    await state.set_state(DealStates.sell_amount)


@dp.message(DealStates.sell_amount)
async def sell_amount(message: Message, state: FSMContext):
    text = message.text.strip()

    # нажали кнопку меню
    if text in MAIN_MENU_BUTTONS:
        await state.clear()
        if text == "💸 Купить USDT":
            return await buy_start(message, state)
        if text == "💵 Продать USDT":
            return await sell_start(message, state)
        if text == "📊 Курс покупки / продажи":
            return await show_course(message, state)

    clean = text.replace(" ", "")
    from rapira_api import fetch_usdt_rub_rate
    rates = await fetch_usdt_rub_rate()
    if not rates:
        await message.answer("⚠️ Не удалось получить курс. Попробуйте позже.")
        return

    sell_rate = rates["sell_from_client"]  # RUB за 1 USDT

    try:
        if clean.upper().endswith("USDT"):
            num = re.sub(r'(?i)USDT$', "", clean)
            usdt_amount = float(num.replace(",", "."))
            rub_amount = usdt_amount * sell_rate
            await message.answer(
                f"💡 Это примерно {rub_amount:.2f} ₽ за {usdt_amount:.6f} USDT."
            )
        else:
            m = re.match(
                r'^([\d.,]+)(?:₽|р\.?|руб\.?|рублей)?$',
                clean,
                flags=re.IGNORECASE,
            )
            if not m:
                raise ValueError("bad format")

            rub_amount = float(m.group(1).replace(" ", "").replace(",", "."))
            usdt_amount = rub_amount / sell_rate
            await message.answer(
                f"💡 Это примерно {usdt_amount:.6f} USDT за {rub_amount:.2f} ₽."
            )
    except ValueError:
        await message.answer(
            "❗ Пожалуйста, введите корректную сумму, например "
            "'50000', '50000 руб' или '200 USDT'."
        )
        return

    await state.update_data(amount=text)
    await state.set_state(DealStates.sell_contact)
    await message.answer(SELL_ASK_CONTACT_TEXT)


@dp.message(DealStates.sell_contact)
async def sell_contact(message: Message, state: FSMContext):
    """Финальный шаг продажи: получили ФИО, шлём заявку админу."""
    data = await state.get_data()
    amount = data.get("amount", "—")
    fio = message.text.strip()

    user = message.from_user
    username = f"@{user.username}" if user.username else user.full_name

    admin_text = (
        "🆕 Новая заявка на ПРОДАЖУ USDT\n\n"
        f"👤 Пользователь: {username} (id: {user.id})\n"
        "📍 Город: Москва\n"
        f"💰 Сумма: {amount}\n"
        f"📄 ФИО для пропуска: {fio}"
    )
    await notify_admin(admin_text)

    await message.answer(SELL_FINISH_TEXT, reply_markup=main_kb)
    await state.clear()


# ---------- КУРС ----------

@dp.message(F.text == "📊 Курс покупки / продажи")
async def show_course(message: Message, state: FSMContext):
    await state.clear()
    from rapira_api import fetch_usdt_rub_rate
    rates = await fetch_usdt_rub_rate()
    if not rates:
        await message.answer("⚠️ Не удалось получить курс. Попробуйте чуть позже.")
    else:
        buy = rates["buy_to_client"]
        sell = rates["sell_from_client"]
        text = (
            f"📊 <b>Курс USDT/RUB (Москва)</b>\n\n"
            f"🟢 Покупка USDT (когда вы покупаете у нас): {buy:.2f} ₽\n"
            f"🔵 Продажа USDT (когда вы продаёте нам): {sell:.2f} ₽"
        )
        await message.answer(text)

    await message.answer(reply_markup=main_kb)


# ---------- ЗАПУСК ----------

async def main():
    print("🔥 SKYNET USDT BOT запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
