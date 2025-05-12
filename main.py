import sys
import logging
import asyncio

from aiogram import Bot, Dispatcher, F, types
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

import gspread
from oauth2client.service_account import ServiceAccountCredentials

from typing import List, Dict, Callable, Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from aiogram.exceptions import TelegramForbiddenError
from typing import Callable, Dict, Any

from config import BOT_TOKEN, CHANNEL_URLS, CHANNEL_IDS, SPREADSHEET_NAME

import asyncio
import logging
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from aiogram.types import Message

valid_subscriptions = ["1 месяц", "3 месяца", "6 месяцев", "12 месяцев"]
user_applications = {}
user_app_index = {}

# Шаги анкеты
class Form(StatesGroup):
    city = State()
    district = State()
    parent_name = State()
    phone = State()
    dou = State()
    child_name = State()
    group = State()
    subscription = State()
    waiting_for_payment_check = State()
    waiting_for_payment_confirmation = State()
    waiting_for_app_number = State()

# Инициализация бота и диспетчера
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# Данные анкеты
user_data = {}
cities = ["Уфа", "Нефтекамск", "Дюртюли", "Агидель", "Янаул", "Амзя", "Николо-Березовка"]
ufa_districts = ["Ленинский", "Кировский", "Советский", "Октябрьский", "Орджоникидзевский", "Калининский", "Демский"]
city_qr_codes = {
    "Уфа": {
        "default": "https://qr.nspk.ru/BS2A00125B2Q1QOD8OFRMANQ8D0IIP01?type=01&bank=100000000284&crc=3ACA",  # Для Уфы
        "Ленинский": "https://qr.nspk.ru/BS2A00125B2Q1QOD8OFRMANQ8D0IIP01?type=01&bank=100000000284&crc=3ACA",  # Для Ленинского района
        "Кировский": "https://qr.nspk.ru/BS2A00125B2Q1QOD8OFRMANQ8D0IIP01?type=01&bank=100000000284&crc=3ACA",  # Для Кировского района
        # Добавьте остальные районы Уфы сюда
    },
    "Нефтекамск": "https://qr.nspk.ru/AS2A006SOSPJL7PP9I1QQK8MEA7M6TOQ?type=01&bank=100000000284&crc=F864",  # Для Нефтекамска
    "Дюртюли": "https://qr.nspk.ru/AS2A006SOSPJL7PP9I1QQK8MEA7M6TOQ?type=01&bank=100000000284&crc=F864",  # Для Дюртюлей
    "Агидель": "https://qr.nspk.ru/AS2A006SOSPJL7PP9I1QQK8MEA7M6TOQ?type=01&bank=100000000284&crc=F864",  # Для Агидели
    "Янаул": "https://qr.nspk.ru/AS2A006SOSPJL7PP9I1QQK8MEA7M6TOQ?type=01&bank=100000000284&crc=F864",  # Для Янаула
    "Амзя": "https://qr.nspk.ru/AS2A006SOSPJL7PP9I1QQK8MEA7M6TOQ?type=01&bank=100000000284&crc=F864",  # Для Амзи
    "Николо-Березовка": "https://qr.nspk.ru/AS2A006SOSPJL7PP9I1QQK8MEA7M6TOQ?type=01&bank=100000000284&crc=F864"  # Для Николо-Березовки
}

qr_links = {
    "Уфа": "https://qr.nspk.ru/BS2A00125B2Q1QOD8OFRMANQ8D0IIP01?type=01&bank=100000000284&crc=3ACA",
    "Орджоникидзевский район": "https://qr.nspk.ru/BS2A0017PQ30HOEH8SFR2BFT8Q788VIO?type=01&bank=100000000284&crc=AC03",
    "Дюртюли": "https://qr.nspk.ru/AS2A006SOSPJL7PP9I1QQK8MEA7M6TOQ?type=01&bank=100000000284&crc=F864",
    "Нефтекамск": "https://qr.nspk.ru/AS2A006SOSPJL7PP9I1QQK8MEA7M6TOQ?type=01&bank=100000000284&crc=F864",
    "Агидель": "https://qr.nspk.ru/AS2A006SOSPJL7PP9I1QQK8MEA7M6TOQ?type=01&bank=100000000284&crc=F864",
    "Янаул": "https://qr.nspk.ru/AS2A006SOSPJL7PP9I1QQK8MEA7M6TOQ?type=01&bank=100000000284&crc=F864",
    "Амзя": "https://qr.nspk.ru/AS2A006SOSPJL7PP9I1QQK8MEA7M6TOQ?type=01&bank=100000000284&crc=F864",
    "Николо-Березовка": "https://qr.nspk.ru/AS2A006SOSPJL7PP9I1QQK8MEA7M6TOQ?type=01&bank=100000000284&crc=F864"
}

logging.basicConfig(level=logging.INFO)

class SubscriptionMiddleware(BaseMiddleware):
    def __init__(self, channel_ids: List[int], channel_urls: Dict[int, str]):
        self.channel_ids = channel_ids
        self.channel_urls = channel_urls
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Any],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        bot = data["bot"]
        user = data.get("event_from_user")

        if not user:
            return await handler(event, data)

        not_subscribed_channels = []

        for channel_id in self.channel_ids:
            try:
                member = await bot.get_chat_member(chat_id=channel_id, user_id=user.id)
                if member.status == "left":
                    not_subscribed_channels.append(channel_id)
            except TelegramForbiddenError:
                logging.warning(f"Бот не может проверить канал {channel_id} — нет прав администратора.")
                continue
            except Exception as e:
                logging.error(f"Ошибка при проверке подписки на канал {channel_id}: {e}")
                continue

        if not_subscribed_channels:
            buttons = [
                [InlineKeyboardButton(text="📢 Подписаться", url=self.channel_urls[channel_id])]
                for channel_id in not_subscribed_channels
            ]
            buttons.append([InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_subscription")])

            await bot.send_message(
                chat_id=user.id,
                text=(
                    "🔒 <b>Доступ ограничен</b>\n\n"
                    "Вы не подписались на все необходимые каналы.\n"
                    "Пожалуйста, подпишитесь и нажмите <b>🔄 Проверить подписку</b>."
                ),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
                parse_mode="HTML"
            )
            return

        return await handler(event, data)

import asyncio
import logging
from aiogram.types import Message
import gspread
from oauth2client.service_account import ServiceAccountCredentials

async def connect_to_sheets(message: Message, creds_path: str, spreadsheet_id: str, sheet_name: str):
    loading_texts = [
        "⏳ Пожалуйста, подождите.",
        "⏳ Пожалуйста, подождите..",
        "⏳ Пожалуйста, подождите..."
    ]

    # Первое сообщение
    loading_msg = await message.answer(loading_texts[0])
    animation_running = True
    previous_text = None

    # Анимация точек
    async def animate_loading():
        nonlocal previous_text
        i = 0
        while animation_running:
            new_text = loading_texts[i % len(loading_texts)]
            if new_text != previous_text:
                try:
                    await loading_msg.edit_text(new_text)
                    previous_text = new_text
                except Exception as e:
                    logging.warning(f"Ошибка при edit_text: {e}")
            await asyncio.sleep(2.5)  # Увеличена задержка
            i += 1

    animation_task = asyncio.create_task(animate_loading())

    # Подключение к Google Sheets
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
        client = gspread.authorize(creds)

        spreadsheet = client.open_by_key(spreadsheet_id)
        sheet = spreadsheet.worksheet(sheet_name)

    except Exception as e:
        animation_running = False
        await animation_task
        await loading_msg.edit_text("❌ Ошибка подключения к Google Таблице.")
        logging.error(f"❌ Ошибка подключения: {e}")
        return None

    animation_running = False
    await animation_task
    await loading_msg.delete()
    logging.info("✅ Успешно подключено к Google Таблице.")
    return sheet

async def send_main_menu(user_id: int, bot: Bot):
    keyboard = ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[
            [KeyboardButton(text="🧾 Оформить подписку")],
            [KeyboardButton(text="🎁 Подарки")],
            [KeyboardButton(text="❓ Часто задаваемые вопросы")],
            [KeyboardButton(text="✉️ Обратная связь")],
            [KeyboardButton(text="📄 Мои заявки")],
            [KeyboardButton(text="💳 Оплатить заказ")]
        ]
    )
    await bot.send_message(
        chat_id=user_id,
        text="Привет! Я — Шустрик, твой помощник 🐿\n\nВыбирай, что тебе интересно:",
        reply_markup=keyboard
    )

@dp.callback_query(F.data == "check_subscription")
async def check_subscription_again(callback: CallbackQuery, bot: Bot, state: FSMContext):
    not_subscribed_channels = []

    for channel_id in CHANNEL_IDS:
        try:
            member = await bot.get_chat_member(chat_id=channel_id, user_id=callback.from_user.id)
            if member.status == "left":
                not_subscribed_channels.append(channel_id)
        except TelegramForbiddenError:
            logging.warning(f"Бот не может проверить канал {channel_id} — нет прав администратора.")
        except Exception as e:
            logging.error(f"Ошибка при повторной проверке подписки на канал {channel_id}: {e}")

    if not_subscribed_channels:
        buttons = [
            [InlineKeyboardButton(text="📢 Подписаться", url=CHANNEL_URLS[channel_id])]
            for channel_id in not_subscribed_channels
        ]
        buttons.append([InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_subscription")])

        await callback.message.edit_text(
            "❗ Вы ещё не подписались на все каналы!\n\nПожалуйста, подпишитесь и повторно нажмите кнопку ниже.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
        return

    await state.clear()
    await callback.message.delete()
    await send_main_menu(callback.from_user.id, bot)

def get_user_rows(sheet, user_id):
    """Возвращает все строки для конкретного Telegram user_id"""
    all_rows = sheet.get_all_records()
    return [row for row in all_rows if str(row.get("user_id")) == str(user_id)]


def get_row_by_number(sheet, number):
    """Возвращает строку по номеру заявки"""
    all_rows = sheet.get_all_records()
    for row in all_rows:
        if str(row.get("application_number")) == str(number):
            return row
    return None

def get_next_application_number(sheet):
    values = sheet.get_all_values()
    
    # Если таблица пуста (только заголовки), начинаем с 1
    if len(values) <= 1:
        return 1  # Первая строка — заголовок
    
    # Получаем все номера заявок из второго столбца (индекс 1)
    application_numbers = [int(row[1]) for row in values[1:] if row[1].isdigit()]
    
    if not application_numbers:
        return 1  # Если в таблице нет номеров заявок, начинаем с 1
    
    # Возвращаем максимальный номер заявки + 1
    return max(application_numbers) + 1

@dp.message(F.text == "/start")
async def cmd_start(message: types.Message, state: FSMContext, bot: Bot):
    await state.clear()
    await send_main_menu(message.from_user.id, bot)

@dp.message(Form.city, F.text == "🔙 Назад в меню")
async def back_to_menu_from_city(message: types.Message, state: FSMContext):
    await state.clear()
    keyboard = ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[
            [KeyboardButton(text="🧾 Оформить подписку")],
            [KeyboardButton(text="🎁 Подарки")],
            [KeyboardButton(text="❓ Часто задаваемые вопросы")],
            [KeyboardButton(text="✉️ Обратная связь")],
            [KeyboardButton(text="📄 Мои заявки")],
            [KeyboardButton(text="💳 Оплатить заказ")]
        ]
    )
    await message.answer("Вы вернулись в главное меню:", reply_markup=keyboard)

@dp.message(F.text == "🧾 Оформить подписку")
async def start_questionnaire(message: types.Message, state: FSMContext):
    keyboard = ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[[KeyboardButton(text=city)] for city in cities] + [[KeyboardButton(text="🔙 Назад в меню")]]
    )
    await message.answer("Выберите ваш город:", reply_markup=keyboard)
    await state.set_state(Form.city)

# Обработка выбора города
@dp.message(Form.city)
async def process_city(message: types.Message, state: FSMContext):
    city = message.text.strip()
    if city not in cities:
        await message.answer("Пожалуйста, выберите город из предложенного списка.")
        return

    await state.update_data(city=city)

    if city == "Уфа":
        # Показываем выбор районов только для Уфы
        keyboard = ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[[KeyboardButton(text=d)] for d in ufa_districts])
        await message.answer("Выберите ваш район:", reply_markup=keyboard)
        await state.set_state(Form.district)
    else:
        # Пропускаем выбор района
        await state.update_data(district="—")
        await message.answer("Введите ФИО родителя:", reply_markup=ReplyKeyboardRemove())
        await state.set_state(Form.parent_name)

# Обработка выбора района
@dp.message(Form.district)
async def process_district(message: types.Message, state: FSMContext):
    district = message.text.strip()
    if district not in ufa_districts:
        await message.answer("Пожалуйста, выберите район из списка.")
        return

    await state.update_data(district=district)
    await message.answer("Введите ФИО родителя:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(Form.parent_name)

# Обработка ФИО родителя
@dp.message(Form.parent_name)
async def process_parent_name(message: types.Message, state: FSMContext):
    await state.update_data(parent_name=message.text)
    await message.answer("Введите номер телефона:")
    await state.set_state(Form.phone)

# Обработка телефона
@dp.message(Form.phone)
async def process_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await message.answer("Введите номер или название ДОУ:")
    await state.set_state(Form.dou)

# Обработка ДОУ
@dp.message(Form.dou)
async def process_dou(message: types.Message, state: FSMContext):
    await state.update_data(dou=message.text)
    await message.answer("Введите ФИО ребёнка:")
    await state.set_state(Form.child_name)

# Обработка ФИО ребёнка
@dp.message(Form.child_name)
async def process_child_name(message: types.Message, state: FSMContext):
    await state.update_data(child_name=message.text)
    await message.answer("Введите группу (например, 'Младшая', 'Средняя'):")
    await state.set_state(Form.group)

@dp.message(Form.group)
async def process_group(message: types.Message, state: FSMContext):
    group = message.text.strip()
    await state.update_data(group=group)

    keyboard = ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[
            [KeyboardButton(text="1 месяц"), KeyboardButton(text="3 месяца")],
            [KeyboardButton(text="6 месяцев"), KeyboardButton(text="12 месяцев")]
        ]
    )
    await message.answer("Выберите срок подписки:", reply_markup=keyboard)
    await state.set_state(Form.subscription)

# Обработка подписки
@dp.message(Form.subscription)
async def process_subscription(message: types.Message, state: FSMContext):
    subscription = message.text.strip()
    valid_options = ["1 месяц", "3 месяца", "6 месяцев", "12 месяцев"]

    keyboard1 = ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[
            [KeyboardButton(text="1 месяц"), KeyboardButton(text="3 месяца")],
            [KeyboardButton(text="6 месяцев"), KeyboardButton(text="12 месяцев")]
        ]
    )
    
    if subscription not in valid_options:
        await message.answer("❗ Пожалуйста, выберите срок подписки из предложенных вариантов.", reply_markup= keyboard1)
        return

    await state.update_data(subscription=subscription)

    data = await state.get_data()
    if not data:
        await message.answer("❗ Произошла ошибка: данные не найдены. Попробуйте начать заново.")
        return

    # Подключение к Google Таблице
    sheet = await connect_to_sheets(
    message,
    "empirical-axon-458108-g5-5b5dc8bbf1b7.json",
    "1J6Mu0nR_mqlWQ1DVmql5WDHzNFZg_7nssWqVFk7ITX4",  # <-- вот ID таблицы
    SPREADSHEET_NAME
    )

    # Получаем следующий номер заявки
    application_number = get_next_application_number(sheet)
    await state.update_data(application_number=application_number)

    # Снова получаем полные данные
    data = await state.get_data()

    row = [
        str(message.from_user.id),
        data.get("application_number", ""),    
        data.get("city", ""),                  
        data.get("district", "-"),             
        data.get("parent_name", ""),           
        data.get("phone", ""),                 
        data.get("dou", ""),                   
        data.get("child_name", ""),            
        data.get("group", ""),                 
        data.get("subscription", "Не выбрана"),
        "False"                                
    ]

    sheet.append_row(row)

    await state.clear()
    
    keyboard = ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[
            [KeyboardButton(text="➕ Добавить ещё ребёнка")],
            [KeyboardButton(text="💳 Оплатить заказ")],
            [KeyboardButton(text="Назад в меню")]
        ]
    )

    await message.answer(
    f"✅ Ваша заявка №{application_number} успешно сохранена!\n"
    "Вы можете добавить ещё ребёнка, оплатить заказ или вернуться в меню."
)
    await message.answer(
        "Следите за статусом заявки в разделе 📄 Мои заявки.",
        reply_markup=keyboard
    )
# --- Обработка нажатия на кнопки после создания заявки ---

@dp.message(F.text == "➕ Добавить ещё ребёнка")
async def add_another_child(message: types.Message, state: FSMContext):
    await state.clear()
    await start_questionnaire(message, state)

subscription_prices = {
    "1 месяц": 150,
    "3 месяца": 375,
    "6 месяцев": 750,
    "12 месяцев": 1125
}

# Получение заявки по номеру
async def get_application_by_number(number, message: types.message):
    sheet = await connect_to_sheets(
    message,
    "empirical-axon-458108-g5-5b5dc8bbf1b7.json",
    "1J6Mu0nR_mqlWQ1DVmql5WDHzNFZg_7nssWqVFk7ITX4",  # <-- вот ID таблицы
    SPREADSHEET_NAME
    )
    
    records = sheet.get_all_records()
    for row in records:
        if str(row.get("Номер заявки", "")).strip() == str(number).strip():
            return row
    return None

# 1️⃣ Пользователь нажал "Оплатить заказ"
@dp.message(F.text == "💳 Оплатить заказ")
async def oplata(message: types.Message, state: FSMContext):
    await message.answer("Введите номер заявки, которую вы хотите оплатить:")
    await state.set_state(Form.waiting_for_payment_check)

# 2️⃣ Обработка номера заявки и показ данных + QR
@dp.message(Form.waiting_for_payment_check)
async def process_payment_request(message: types.Message, state: FSMContext):
    try:
        request_number = message.text.strip()
        request = await get_application_by_number(request_number, message)  # <-- исправлено

        if not request:
            await message.answer("❌ Заявка с таким номером не найдена.")
            return

        city = request.get("Город", "")
        district = request.get("Район", "—")
        subscription = request.get("Подписка", "")
        price = str(request.get("Сумма", "")).strip()

        # Автоматически установить цену, если она не указана
        if not price and subscription in subscription_prices:
            price = subscription_prices[subscription]

        if not price:
            await message.answer("⚠️ Не удалось определить сумму к оплате.")
            return

        # Получаем нужную ссылку
        if city == "Уфа" and district == "Орджоникидзевский район":
            qr_url = qr_links.get("Орджоникидзевский район")
        else:
            qr_url = qr_links.get(city, qr_links["Дюртюли"])  # По умолчанию, если нет ссылки

        # Кнопки: Перейти к оплате и Я оплатил
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💳 Перейти к оплате", url=qr_url)],
                [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"confirm_payment:{request_number}")]
            ]
        )

        text = (
            f"📄 Заявка №{request_number}\n"
            f"🌍 Город: {city}\n"
            f"🏘 Район: {district}\n"
            f"📦 Подписка: {subscription}\n"
            f"💰 Сумма к оплате: {price} руб.\n\n"
            f"🔽 Нажмите кнопку ниже, чтобы перейти к оплате.\n"
            f"После оплаты нажмите '✅ Я оплатил'."
        )

        await message.answer(text, reply_markup=keyboard)

        # Сохраняем номер заявки в состоянии
        await state.update_data(application_number=request_number)
        await state.set_state(Form.waiting_for_payment_confirmation)

    except Exception as e:
        await message.answer("⚠️ Произошла ошибка при обработке заявки.")
        print(e)

# 3️⃣ Подтверждение оплаты
@dp.callback_query(F.data.startswith("confirm_payment:"))
async def handle_confirm_payment_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()  # Закрываем "часики"

    application_number = callback.data.split(":")[1]

    sheet = await connect_to_sheets(
        callback.message,
        "empirical-axon-458108-g5-5b5dc8bbf1b7.json",
        "1J6Mu0nR_mqlWQ1DVmql5WDHzNFZg_7nssWqVFk7ITX4",
        SPREADSHEET_NAME
    )
    if not sheet:
        await callback.message.answer("🚫 Не удалось подключиться к таблице. Попробуйте позже.")
        return

    records = sheet.get_all_records()
    for row in records:
        if str(row.get("Номер заявки", "")).strip() == application_number:
            status = str(row.get("Статус оплаты", "")).strip().lower()
            if status == "true":
                await callback.message.answer(f"✅ Оплата по заявке №{application_number} уже подтверждена!")
            else:
                await callback.message.answer(f"⏳ Оплата по заявке №{application_number} ещё не подтверждена. Пожалуйста, подождите.")
            break
    else:
        await callback.message.answer("❗ Заявка не найдена. Проверьте номер.")

    await state.clear()


# --- Мои заявки ---

# --- Получение заявок пользователя из Google Sheets ---
def get_user_applications(user_id: str, sheet):
    records = sheet.get_all_records()
    # Фильтрация по user_id
    apps = [row for row in records if str(row.get("user_id")) == str(user_id)]
    # Сортировка: от последних к первым (если есть поле "Номер заявки", сортируем по нему)
    apps.sort(key=lambda r: int(r.get("Номер заявки", 0)), reverse=True)
    return apps

# --- Обработчик кнопки "📄 Мои заявки" ---
@dp.message(F.text == "📄 Мои заявки")
async def handle_my_applications(message: types.Message):
    sheet = await connect_to_sheets(
    message,
    "empirical-axon-458108-g5-5b5dc8bbf1b7.json",
    "1J6Mu0nR_mqlWQ1DVmql5WDHzNFZg_7nssWqVFk7ITX4",  # <-- вот ID таблицы
    SPREADSHEET_NAME
    )
    if sheet is None:
        return

    user_id = str(message.from_user.id)
    apps = get_user_applications(user_id, sheet)

    if not apps:
        await message.answer("❗ У вас нет заявок.")
        return

    user_applications[user_id] = apps
    user_app_index[user_id] = 0
    await send_application(message, user_id)

# --- Отправка одной заявки ---
async def send_application(message_or_callback, user_id: str):
    apps = user_applications.get(user_id, [])
    index = user_app_index.get(user_id, 0)

    if not apps or index >= len(apps):
        await message_or_callback.answer("❗ Не удалось отобразить заявку.")
        return

    app = apps[index]
    status = str(app.get("Статус оплаты", "")).strip().lower()
    status_text = "✅ Оплачено" if status == "true" else "❌ Не оплачено"

    text = (
        f"📄 Заявка №{app.get('Номер заявки')}\n\n"
        f"🏙 Город: {app.get('Город')}\n"
        f"📍 Район: {app.get('Район')}\n"
        f"👤 Родитель: {app.get('ФИО родителя')}\n"
        f"📞 Телефон: {app.get('Телефон')}\n"
        f"🏫 ДОУ: {app.get('ДОУ')}\n"
        f"🧒 Ребёнок: {app.get('ФИО ребенка')}\n"
        f"👥 Группа: {app.get('Группа')}\n"
        f"🛒 Подписка: {app.get('Подписка')}\n"
        f"💵 Статус оплаты: {status_text}"
    )

    nav_buttons = []
    if index > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Предыдущая", callback_data="prev_app"))
    if index < len(apps) - 1:
        nav_buttons.append(InlineKeyboardButton(text="➡️ Следующая", callback_data="next_app"))

    keyboard = InlineKeyboardMarkup(inline_keyboard=[nav_buttons]) if nav_buttons else None
    await message_or_callback.answer(text, reply_markup=keyboard)

# --- Следующая заявка ---
@dp.callback_query(F.data == "next_app")
async def next_application(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    if user_app_index.get(user_id, 0) < len(user_applications.get(user_id, [])) - 1:
        user_app_index[user_id] += 1
    else:
        await callback.answer("Это последняя заявка.")
        return
    await update_application(callback)

# --- Предыдущая заявка ---
@dp.callback_query(F.data == "prev_app")
async def prev_application(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    if user_app_index.get(user_id, 0) > 0:
        user_app_index[user_id] -= 1
    else:
        await callback.answer("Это первая заявка.")
        return
    await update_application(callback)

# --- Обновление текста заявки ---
async def update_application(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    apps = user_applications.get(user_id, [])
    index = user_app_index.get(user_id, 0)

    if not apps or index >= len(apps):
        await callback.answer("❗ Не удалось отобразить заявку.")
        return

    app = apps[index]
    status = str(app.get("Статус оплаты", "")).strip().lower()
    status_text = "✅ Оплачено" if status == "true" else "❌ Не оплачено"

    text = (
        f"📄 Заявка №{app.get('Номер заявки')}\n\n"
        f"🏙 Город: {app.get('Город')}\n"
        f"📍 Район: {app.get('Район')}\n"
        f"👤 Родитель: {app.get('ФИО родителя')}\n"
        f"📞 Телефон: {app.get('Телефон')}\n"
        f"🏫 ДОУ: {app.get('ДОУ')}\n"
        f"🧒 Ребёнок: {app.get('ФИО ребенка')}\n"
        f"👥 Группа: {app.get('Группа')}\n"
        f"🛒 Подписка: {app.get('Подписка')}\n"
        f"💵 Статус оплаты: {status_text}"
    )

    nav_buttons = []
    if index > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Предыдущая", callback_data="prev_app"))
    if index < len(apps) - 1:
        nav_buttons.append(InlineKeyboardButton(text="➡️ Следующая", callback_data="next_app"))

    keyboard = InlineKeyboardMarkup(inline_keyboard=[nav_buttons]) if nav_buttons else None
    await callback.message.edit_text(text, reply_markup=keyboard)

# --- Подарки, FAQ, Обратная связь ---

@dp.message(F.text == "🎁 Подарки")
async def gifts(message: types.Message):
    await message.answer(
        "🎁 На данный момент подарков нет. Следите за новыми акциями и предложениями!"
    )

@dp.message(F.text == "❓ Часто задаваемые вопросы")
async def faq(message: types.Message):
    await message.answer(
        "❓ Вопросы и ответы:\n\n"
        "1. Как оформить подписку?\n"
        "Для оформления подписки выберите пункт 'Оформить подписку' в главном меню и следуйте инструкциям.\n\n"
        "2. Как оплатить?\n"
        "После выбора подписки вам будет предоставлен QR-код для оплаты. Следуйте инструкциям на экране.\n\n"
        "3. Как получить подарок?\n"
        "На данный момент подарков нет. Следите за новыми акциями и предложениями!\n\n"
        "4. Где посмотреть статус своей заявки?\n"
        "Вы можете проверить статус своей заявки в разделе 'Мои заявки'."
    )

@dp.message(F.text == "✉️ Обратная связь")
async def feedback(message: types.Message):
    text = (
        "📞 <b>Связь с поддержкой</b>\n\n"
        "Если у вас есть вопросы по участию в проекте <b>«Шустрики»</b>, пожалуйста, свяжитесь с нами через WhatsApp.\n"
        "Если вы столкнулись с техническими проблемами или у вас есть предложения по работе бота — пишите напрямую разработчику в Telegram.\n\n"
        "💬 <b>WhatsApp (по проекту «Шустрики»):</b>\n"
        "<a href='https://wa.me/79968831020'>+7 996 883-10-20</a>\n\n"
        "📨 <b>Telegram (по работе бота):</b>\n"
        "<a href='https://t.me/Heimdall_SM'>@Heimdall_SM</a>\n\n"
        "⌛️ Мы стараемся отвечать максимально быстро. Спасибо за ваше обращение! 🙌"
    )
    await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)


@dp.message(F.text == "Назад в меню")
async def back_to_menu(message: types.Message, state: FSMContext, bot: Bot):
    user_data.pop(message.from_user.id, None)  # Очистка данных пользователя
    await state.clear()  # Завершаем текущее состояние пользователя
    await cmd_start(message, state, bot)  # Передаем bot

# --- Запуск бота ---

if __name__ == "__main__":
    dp.message.middleware(SubscriptionMiddleware(CHANNEL_IDS, CHANNEL_URLS))
    asyncio.run(dp.start_polling(bot))
