import asyncio
import re
from datetime import datetime

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
    BUY_ASK_CONTACT_TEXT,
    BUY_FINISH_TEXT,
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


def generate_order_id() -> str:
    """Простой номер заявки по текущему времени."""
    return datetime.now().strftime("%y%m%d%H%M%S")


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

    await message.answer(
        f"💸 <b>Покупка USDT (Москва)</b>\n\n"
        f"Курс: {buy_rate:.2f} ₽\n\n"
        "Укажите, пожалуйста, сумму обмена в рублях:\n"
    )
    await state.set_state(DealStates.buy_amount)


@dp.message(DealStates.buy_amount)
async def buy_amount(message: Message, state: FSMContext):
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

    buy_rate = rates["buy_to_client"]  # RUB за 1 USDT

    try:
        # вариант, когда ввели USDT
        if clean.upper().endswith("USDT"):
            num = re.sub(r"(?i)USDT$", "", clean)
            usdt_amount = float(num.replace(",", "."))
            rub_amount = usdt_amount * buy_rate
        else:
            # считаем, что ввели рубли
            m = re.match(
                r"^([\d.,]+)(?:₽|р\.?|руб\.?|рублей)?$",
                clean,
                flags=re.IGNORECASE,
            )
            if not m:
                raise ValueError("bad format")

            rub_amount = float(m.group(1).replace(",", "."))
            usdt_amount = rub_amount / buy_rate

        # --- окно заявки ---
        order_id = generate_order_id()
        usdt_rounded = int(round(usdt_amount))

        text_window = (
            f"🧾 <b>Заявка #{order_id}</b>\n\n"
            f"Вы отдаёте: {rub_amount:.2f} ₽\n"
            f"Вы получаете: {usdt_rounded} USDT\n"
            f"Курс обмена: {buy_rate:.2f} ₽ за 1 USDT\n\n"
            "ℹ️ Точная сумма будет рассчитана по фактическому курсу "
            "на момент пересчёта денег."
        )

        await message.answer(text_window)

    except Exception:
        await message.answer(
            "❗ Пожалуйста, введите корректную сумму.\n"

        )
        return

    # сохраняем данные для заявки
    await state.update_data(
        amount_input=text,          # как ввёл пользователь
        order_id=order_id,
        rub_amount=rub_amount,
        usdt_amount=usdt_rounded,   # округлённое значение
        rate=buy_rate,
        direction="buy",
    )

    await state.set_state(DealStates.buy_contact)
    await message.answer(BUY_ASK_CONTACT_TEXT)



@dp.message(DealStates.buy_contact)
async def buy_contact(message: Message, state: FSMContext):
    """Финальный шаг покупки: получили ФИО, шлём заявку админу."""

    text = message.text.strip()

    # Если вместо ФИО нажали кнопку меню — переключаем сценарий
    if text in MAIN_MENU_BUTTONS:
        await state.clear()
        if text == "💸 Купить USDT":
            return await buy_start(message, state)
        if text == "💵 Продать USDT":
            return await sell_start(message, state)
        if text == "📊 Курс покупки / продажи":
            return await show_course(message, state)

    data = await state.get_data()
    order_id = data.get("order_id", "—")
    amount_input = data.get("amount_input", "—")
    rub_amount = data.get("rub_amount")
    usdt_amount = data.get("usdt_amount")
    rate = data.get("rate")

    fio = text

    user = message.from_user
    username = f"@{user.username}" if user.username else user.full_name

    # Формируем красивое окно для админа
    admin_text = (
        f"🧾 Заявка #{order_id}\n"
        "🆕 Новая заявка на ПОКУПКУ USDT\n\n"
        f"👤 Пользователь: {username} (id: {user.id})\n"
        "📍 Город: Москва\n"
        f"🔢 Ввод пользователя: {amount_input}\n"
        f"💳 Клиент ОТДАЁТ: {rub_amount:.2f} ₽\n"
        f"💰 Клиент ПОЛУЧАЕТ: {usdt_amount} USDT\n"
        f"📈 Курс: {rate:.2f} ₽ за 1 USDT\n\n"
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

    sell_rate = rates["sell_from_client"]  # RUB за 1 USDT

    await message.answer(
        f"💵 <b>Продажа USDT (Москва)</b>\n\n"
        f"Курс: {sell_rate:.2f} ₽\n\n"
        "Укажите, пожалуйста, сумму обмена в USDT:\n"
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
            num = re.sub(r"(?i)USDT$", "", clean)
            usdt_amount = float(num.replace(",", "."))
            rub_amount = usdt_amount * sell_rate
        else:
            m = re.match(
                r"^([\d.,]+)(?:₽|р\.?|руб\.?|рублей)?$",
                clean,
                flags=re.IGNORECASE,
            )
            if not m:
                raise ValueError("bad format")

            rub_amount = float(m.group(1).replace(",", "."))
            usdt_amount = rub_amount / sell_rate

        order_id = generate_order_id()
        rub_rounded = int(round(rub_amount))

        text_window = (
            f"🧾 <b>Заявка #{order_id}</b>\n\n"
            f"Вы отдаёте: {usdt_amount:.2f} USDT\n"
            f"Вы получаете: {rub_rounded} ₽\n"
            f"Курс обмена: {sell_rate:.2f} ₽ за 1 USDT\n\n"
            "ℹ️ Точная сумма будет рассчитана по фактическому курсу "
            "на момент пересчёта денег."
        )

        await message.answer(text_window)

    except Exception:
        await message.answer(
            "❗ Пожалуйста, введите корректную сумму.\n"
        )
        return

    await state.update_data(
        amount_input=text,
        order_id=order_id,
        rub_amount=rub_rounded,     # здесь рубли округлены
        usdt_amount=usdt_amount,
        rate=sell_rate,
        direction="sell",
    )

    await state.set_state(DealStates.sell_contact)
    await message.answer(SELL_ASK_CONTACT_TEXT)



@dp.message(DealStates.sell_contact)
async def sell_contact(message: Message, state: FSMContext):
    """Финальный шаг продажи: получили ФИО, шлём заявку админу."""

    text = message.text.strip()

    # Если вместо ФИО нажали кнопку меню — переключаем сценарий
    if text in MAIN_MENU_BUTTONS:
        await state.clear()
        if text == "💸 Купить USDT":
            return await buy_start(message, state)
        if text == "💵 Продать USDT":
            return await sell_start(message, state)
        if text == "📊 Курс покупки / продажи":
            return await show_course(message, state)

    data = await state.get_data()
    order_id = data.get("order_id", "—")
    amount_input = data.get("amount_input", "—")
    rub_amount = data.get("rub_amount")
    usdt_amount = data.get("usdt_amount")
    rate = data.get("rate")

    fio = text

    user = message.from_user
    username = f"@{user.username}" if user.username else user.full_name

    admin_text = (
        f"🧾 Заявка #{order_id}\n"
        "🆕 Новая заявка на ПРОДАЖУ USDT\n\n"
        f"👤 Пользователь: {username} (id: {user.id})\n"
        "📍 Город: Москва\n"
        f"🔢 Ввод пользователя: {amount_input}\n"
        f"💳 Клиент ОТДАЁТ: {usdt_amount:.2f} USDT\n"
        f"💰 Клиент ПОЛУЧАЕТ: {rub_amount} ₽\n"
        f"📉 Курс: {rate:.2f} ₽ за 1 USDT\n\n"
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
            "📊 <b>Курс USDT/RUB (Москва)</b>\n\n"
            f"🟢 Покупка USDT (когда вы покупаете у нас): {buy:.2f} ₽\n"
            f"🔵 Продажа USDT (когда вы продаёте нам): {sell:.2f} ₽"
        )
        await message.answer(text)

    await message.answer("Выберите дальнейшее действие:", reply_markup=main_kb)


# ---------- ЗАПУСК ----------

async def main():
    print("🔥 SKYNET USDT BOT запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
