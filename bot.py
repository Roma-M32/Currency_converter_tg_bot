import os
from dotenv import load_dotenv
import logging
import requests
import xml.etree.ElementTree as ET
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

# Загружаем переменные из .env
load_dotenv()

# Вводим свой токен
TOKEN = os.getenv('BOT_TOKEN')

# API Центробанка РФ
CBR_API_URL = 'https://www.cbr.ru/scripts/XML_daily.asp'

# Логирование
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Создаем бота и диспетчер
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Определяем состояния для FSM
class ConvertState(StatesGroup):
    waiting_for_amount = State()
    waiting_for_currency_from = State()
    waiting_for_currency_to = State()
    waiting_for_restart = State()

class RateState(StatesGroup):
    waiting_for_currency = State()

# Словарь обозначений валют
currency_aliases = {
    'доллар': ('USD', 'Доллар США'),
    'доллары': ('USD', 'Доллар США'),
    'баксы': ('USD', 'Доллар США'),
    'евро': ('EUR', 'Евро'),
    'рубль': ('RUB', 'Российский рубль'),
    'рубли': ('RUB', 'Российский рубль'),
    'йена': ('JPY', 'Японская иена'),
    'иена': ('JPY', 'Японская иена'),
    'фунт': ('GBP', 'Британский фунт'),
    'фунты': ('GBP', 'Британский фунт'),
    'юань': ('CNY', 'Китайский юань'),
    'юани': ('CNY', 'Китайский юань'),
    'динар': ('RSD', 'Сербский динар'),
    'динары': ('RSD', 'Сербский динар'),
    'тенге': ('KZT', 'Казахстанский тенге'),
    'рупия': ('INR', 'Индийская рупия'),
    'рупии': ('INR', 'Индийская рупия')
}

# Функция для перевода названий валют в коды
def get_currency_code(user_input):
    user_input = user_input.lower().strip()
    return currency_aliases.get(user_input, (user_input.upper(), user_input.upper()))

# Функция для получения курсов валют с сайта ЦБ РФ
def get_exchange_rates():
    response = requests.get(CBR_API_URL)
    if response.status_code != 200:
        return {}

    rates = {'RUB': 1.0}  # Рубль принимаем за 1.0
    root = ET.fromstring(response.content)

    for valute in root.findall('Valute'):
        char_code = valute.find('CharCode').text  # Код валюты (USD, EUR и т. д.)
        value = float(valute.find('Value').text.replace(',', '.'))  # Курс к рублю
        nominal = int(valute.find('Nominal').text)  # Количество единиц валюты (например, 100 JPY)
        rates[char_code] = value / nominal  # Приводим курс к 1 единице валюты

    return rates

    # Пересчитываем все курсы ОТНОСИТЕЛЬНО РУБЛЯ
    for currency in rates:
        rates[currency] = 1 / rates[currency]  # Делаем из RUB базовую валюту

    return rates

# Главное меню с кнопками "💱 Конвертация" , "📊 Узнать курс" и "🚪 Выйти"
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='💱 Конвертация')],
        [KeyboardButton(text='📊 Узнать курс')],
        [KeyboardButton(text='🚪 Выйти')]
    ],
    resize_keyboard=True
)

# Кнопки "✅ Да" и "❌ Нет"
restart_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text='✅ Да'), KeyboardButton(text='❌ Нет')]],
    resize_keyboard=True
)

# Функция логирования сообщений пользователя
async def log_user_message(message: Message):
    user = message.from_user
    logging.info(f'👤 {user.full_name} (ID: {user.id}, Username: @{user.username}) → {message.text}')

# Обработчик команды /start (приветствие по имени)
@dp.message(Command('start'))
async def start_command(message: Message):
    await log_user_message(message)
    
    # Получаем имя пользователя (если нет, используем "друг")
    user_name = message.from_user.first_name if message.from_user.first_name else "друг"

    await message.answer(
        f'Привет, {user_name}! 😊\n\nВыберите действие ниже:', 
        reply_markup=main_keyboard
    )


# Обработчик кнопки "📊 Узнать курс"
@dp.message(lambda message: message.text == '📊 Узнать курс')
async def get_rate_start(message: Message, state: FSMContext):
    await log_user_message(message)
    await message.answer('Введите валюту, курс которой хотите узнать (например, USD, евро, рубли):')
    await state.set_state(RateState.waiting_for_currency)

# Получаем валюту и выводим курс к рублю
@dp.message(RateState.waiting_for_currency)
async def process_currency_rate(message: Message, state: FSMContext):
    await log_user_message(message)
    currency, currency_name = get_currency_code(message.text)

    rates = get_exchange_rates()
    if currency not in rates:
        await message.answer('❌ Неправильная валюта. Введите еще раз (например, USD, евро, рубли):')
        return

    rate = rates[currency]
    
    # Показываем курс валюты
    await message.answer(
        f'📊 Курс {currency} ({currency_name}) к рублю: **1 {currency} = {rate:.2f} RUB**\n📌 Курс по данным Центробанка РФ.',
        parse_mode='Markdown'
    )

    # После просмотра курса предлагаем выбор действия
    action_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='💱 Конвертация')],
            [KeyboardButton(text='📊 Узнать курс')],
            [KeyboardButton(text='🚪 Выйти')]
        ],
        resize_keyboard=True
    )
    
    await message.answer('Что хотите сделать дальше?', reply_markup=action_keyboard)
    await state.clear()

# Обработчик кнопки "💱 Конвертация"
@dp.message(lambda message: message.text == '💱 Конвертация')
@dp.message(Command('convert'))
async def start_conversion(message: Message, state: FSMContext):
    await log_user_message(message)
    await message.answer('Введите сумму для конвертации:', reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(ConvertState.waiting_for_amount)

# Получаем исходную валюту
@dp.message(ConvertState.waiting_for_amount)
async def process_amount(message: Message, state: FSMContext):
    await log_user_message(message)
    try:
        amount = float(message.text)
        await state.update_data(amount=amount)
        await message.answer('Введите валюту, из которой конвертируем (например, USD, евро, рубли):')
        await state.set_state(ConvertState.waiting_for_currency_from)
    except ValueError:
        await message.answer('❌ Пожалуйста, введите корректное число.')

# Получаем валюту "из которой" конвертируем
@dp.message(ConvertState.waiting_for_currency_from)
async def process_currency_from(message: Message, state: FSMContext):
    await log_user_message(message)
    currency_from, currency_name_from = get_currency_code(message.text)

    rates = get_exchange_rates()
    if currency_from not in rates:
        await message.answer('❌ Неправильная валюта. Введите еще раз (например, USD, евро, рубли):')
        return

    await state.update_data(currency_from=currency_from, currency_name_from=currency_name_from)
    await message.answer('Введите валюту, в которую хотите конвертировать (например, EUR, доллары, юани):')
    await state.set_state(ConvertState.waiting_for_currency_to)

# Обрабатываем "✅ Да" (продолжить) и "❌ Нет" (предложение выбора)
@dp.message(ConvertState.waiting_for_restart)
async def restart_or_end(message: Message, state: FSMContext):
    await log_user_message(message)
    if message.text == '✅ Да':
        await message.answer('Введите сумму для конвертации:', reply_markup=types.ReplyKeyboardRemove())
        await state.set_state(ConvertState.waiting_for_amount)
    elif message.text == '❌ Нет':
        # Предлагаем выбор действия
        action_keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text='💱 Конвертация')],
                [KeyboardButton(text='📊 Узнать курс')],
                [KeyboardButton(text='🚪 Выйти')]
            ],
            resize_keyboard=True
        )
        await message.answer('Что хотите сделать дальше?', reply_markup=action_keyboard)
        await state.clear()


# Завершаем конвертацию
@dp.message(ConvertState.waiting_for_currency_to)
async def process_currency_to(message: Message, state: FSMContext):
    await log_user_message(message)
    currency_to, currency_name_to = get_currency_code(message.text)
    user_data = await state.get_data()

    amount = user_data['amount']
    currency_from = user_data['currency_from']
    currency_name_from = user_data['currency_name_from']

    rates = get_exchange_rates()

    if currency_to not in rates:
        await message.answer('❌ Неправильная валюта. Введите еще раз (например, USD, евро, рубли):')
        return

    converted_amount = amount * (rates[currency_from] / rates[currency_to])

    await message.answer(
        f'✅ {amount} {currency_from} ({currency_name_from}) = {converted_amount:.2f} {currency_to} ({currency_name_to})\n📌 Курс по данным Центробанка РФ.'
        '\n\n❓ Хотите сделать ещё одну конвертацию?',
        reply_markup=restart_keyboard
    )

    await state.set_state(ConvertState.waiting_for_restart)

# Обработчик кнопки "🚪 Выйти"
@dp.message(lambda message: message.text == '🚪 Выйти')
async def exit_bot(message: Message):
    await log_user_message(message)
    await message.answer('Спасибо за использование бота! 😊\nЕсли захотите снова сконвертировать валюту или узнать курс, просто нажмите /start.', 
                         reply_markup=types.ReplyKeyboardRemove())

# Обработчик неверного ввода после вопроса "Что хотите сделать дальше?"
@dp.message()
async def handle_unexpected_message(message: Message):
    await log_user_message(message)
    
    # Отправляем сообщение с просьбой выбрать кнопку
    await message.answer('❌ Пожалуйста, выберите один из вариантов ниже:', reply_markup=ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='💱 Конвертация')],
            [KeyboardButton(text='📊 Узнать курс')],
            [KeyboardButton(text='🚪 Выйти')]
        ],
        resize_keyboard=True
    ))

# Запуск бота
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
