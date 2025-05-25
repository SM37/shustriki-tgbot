"""
Telegram bot for selling subscriptions via SBP QR-codes through Tochka Bank
===========================================================================

(Обновлён под официальную документацию Точки — используется endpoint /v1/acquiring/payments)
"""

import os
import uuid
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.client.default import DefaultBotProperties

import aiohttp
from aiohttp.client_exceptions import ClientError

# ---------------------------------------------------------------------------
#  Загрузка переменных окружения (.env)
# ---------------------------------------------------------------------------

try:
    from dotenv import load_dotenv  # type: ignore
    ENV_PATH = Path(__file__).resolve().parent / ".env"
    load_dotenv(dotenv_path=ENV_PATH, override=False)
except ImportError:
    def load_dotenv(*_args, **_kwargs):
        pass

# ---------------------------------------------------------------------------
#  Настройки
# ---------------------------------------------------------------------------

BOT_TOKEN = os.getenv("BOT_TOKEN")
TOCHKA_TOKEN = os.getenv("TOCHKA_TOKEN")
TOCHKA_CLIENT_ID = os.getenv("TOCHKA_CLIENT_ID")
TOCHKA_CUSTOMER_CODE = os.getenv("TOCHKA_CUSTOMER_CODE")

if not all([BOT_TOKEN, TOCHKA_TOKEN, TOCHKA_CLIENT_ID, TOCHKA_CUSTOMER_CODE]):
    raise RuntimeError("Не заданы все переменные окружения. Проверьте .env")

API_BASE = "https://api.tochka.com/api"

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ---------------------------------------------------------------------------
#  Константы
# ---------------------------------------------------------------------------

PRICES_RUB = {
    "1 месяц": 100.0,
    "3 месяца": 270.0,
    "6 месяцев": 510.0,
    "12 месяцев": 960.0,
}

CITIES = ["Уфа", "Янаул", "Березовка"]

class Form(StatesGroup):
    city = State()
    period = State()

aiohttp_session: aiohttp.ClientSession | None = None

async def get_session() -> aiohttp.ClientSession:
    global aiohttp_session
    if aiohttp_session is None or aiohttp_session.closed:
        aiohttp_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=20),
            headers={
                "Authorization": f"Bearer {TOCHKA_TOKEN}",
                "X-Client-Id": TOCHKA_CLIENT_ID,
                "Content-Type": "application/json",
            },
        )
    return aiohttp_session

async def close_session() -> None:
    if aiohttp_session and not aiohttp_session.closed:
        await aiohttp_session.close()

async def create_sbp_qr(amount_rub: float, purpose: str) -> str:
    session = await get_session()
    url = f"{API_BASE}/v1/acquiring/payments"
    payload = {
        "customerCode": TOCHKA_CUSTOMER_CODE,
        "amount": int(round(amount_rub * 100)),
        "purpose": purpose,
        "paymentMode": "sbp",
        "redirectUrl": "https://example.com/thankyou"
    }
    async with session.post(url, json=payload) as resp:
        text = await resp.text()
        if resp.status != 200:
            logger.error("QR API error: %s", text)
            raise RuntimeError(f"Ошибка QR API: {resp.status} — {text}")
        data = await resp.json()
        return data["paymentLink"]

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    kb = [[KeyboardButton(text=city)] for city in CITIES]
    await message.answer("<b>🏙 Выберите город подписки:</b>", reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))
    await state.set_state(Form.city)

@dp.message(Form.city)
async def process_city(message: Message, state: FSMContext) -> None:
    city = message.text.strip()
    if city not in CITIES:
        await message.answer("⛔ Такого города нет.")
        return
    await state.update_data(city=city)
    kb = [[KeyboardButton(text=period)] for period in PRICES_RUB]
    await message.answer("<b>📅 Выберите срок подписки:</b>", reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))
    await state.set_state(Form.period)

@dp.message(Form.period)
async def create_invoice(message: Message, state: FSMContext) -> None:
    period = message.text.strip()
    if period not in PRICES_RUB:
        await message.answer("⛔ Некорректный срок.")
        return

    data = await state.get_data()
    city = data.get("city")
    amount = PRICES_RUB[period]
    purpose = f"Подписка {city} - {period}"

    try:
        qr_url = await create_sbp_qr(amount, purpose)
    except Exception as exc:
        await message.answer("❌ Ошибка генерации ссылки. Попробуйте позже.")
        logger.exception("QR error: %s", exc)
        await state.clear()
        return

    await message.answer(
        f"<b>💳 Оплата подписки</b>\n\n"
        f"Город: <b>{city}</b>\n"
        f"Период: <b>{period}</b>\n"
        f"Сумма: <b>{amount:.2f} ₽</b>\n\n"
        f"Ссылка на оплату через СБП:\n{qr_url}\n\n"
        "После оплаты бот автоматически подтвердит её."
    )
    await state.clear()

# Запуск

def main() -> None:
    try:
        dp.run_polling(bot)
    finally:
        asyncio.run(close_session())

if __name__ == "__main__":
    main()
