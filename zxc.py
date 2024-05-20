main.py
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils import executor
from handlers import register_handlers
from db import setup_db
import aioschedule

API_TOKEN = '6790788175:AAFylgos7EQjJWY1zPc6Vp9gw0o8RBjYupQ'

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

def setup_dispatcher():
    setup_db()
    register_handlers(dp)

async def scheduler():
    while True:
        print("Running scheduled tasks...")
        await aioschedule.run_pending()
        await asyncio.sleep(1)

def main():
    loop = asyncio.get_event_loop()
    setup_dispatcher()
    loop.create_task(scheduler())  # Запускаем планировщик как задачу в цикле событий
    executor.start_polling(dp, skip_updates=True)

if __name__ == '__main__':
    main()
db.py
import sqlite3
from datetime import datetime

def create_connection():
    return sqlite3.connect('bot.db')

def setup_db():
    conn = create_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_selections (
            user_id INTEGER PRIMARY KEY,
            date TEXT,
            time TEXT,
            workout_program TEXT
        )
    ''')
    conn.commit()
    conn.close()

def save_user_selection(user_id, date, time, workout_program=None):
    conn = create_connection()
    c = conn.cursor()
    if workout_program:
        c.execute("""
            INSERT INTO user_selections (user_id, date, time, workout_program) 
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET 
                date=excluded.date, 
                time=excluded.time,
                workout_program=excluded.workout_program;
        """, (user_id, date, time, workout_program))
    else:
        c.execute("""
            INSERT INTO user_selections (user_id, date, time) 
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET 
                date=excluded.date, 
                time=excluded.time;
        """, (user_id, date, time))
    conn.commit()
    conn.close()

def get_user_selection(user_id):
    conn = create_connection()
    c = conn.cursor()
    c.execute("SELECT date, time, workout_program FROM user_selections WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    print("Retrieved from DB:", result)  # Логирование для отладки
    return result

def get_todays_workouts():
    today = datetime.now().strftime("%Y-%m-%d")
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, time FROM user_selections WHERE date = ?", (today,))
    workouts = [{'user_id': row[0], 'time': row[1]} for row in cursor.fetchall()]
    conn.close()
    return workouts
utils.py
from datetime import datetime, timedelta
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from calendar import monthrange
import aioschedule
from aiogram import Bot
from datetime import datetime, timedelta
import asyncio
from db import get_todays_workouts


def read_welcome_message():
    with open('privet.txt', 'r', encoding='utf-8') as file:
        return file.read()

def read_newbie_info():
    with open('info.txt', 'r', encoding='utf-8') as file:
        return file.read()

def create_calendar(year=None, month=None):
    if not year:
        year = datetime.now().year
    if not month:
        month = datetime.now().month

    markup = InlineKeyboardMarkup(row_width=7)
    days_in_month = monthrange(year, month)[1]
    markup.row(
        InlineKeyboardButton("<", callback_data=f"prev-month_{year}_{month}"),
        InlineKeyboardButton(f"{year}-{month:02}", callback_data="ignore"),
        InlineKeyboardButton(">", callback_data=f"next-month_{year}_{month}")
    )
    for day in range(1, days_in_month + 1):
        markup.insert(InlineKeyboardButton(str(day), callback_data=f"day_{year}-{month:02}-{day}"))
    return markup

async def send_reminder(bot, chat_id, message):
    print(f"Sending reminder to {chat_id}")
    try:
        await bot.send_message(chat_id, message)
        print(f"Reminder sent to {chat_id}")
    except Exception as e:
        print(f"Failed to send reminder to {chat_id}: {e}")

async def schedule_training_reminders(bot):
    workouts = get_todays_workouts()
    now = datetime.now()
    print(f"Current time: {now}")

    for workout in workouts:
        workout_time = datetime.strptime(f"{workout['date']} {workout['time']}", "%Y-%m-%d %H:%M")
        reminder_time = workout_time - timedelta(minutes=1)
        reminder_time_str = reminder_time.strftime("%H:%M")
        print(f"Scheduled for: {workout_time}, reminder at: {reminder_time_str}")

        if reminder_time > now:
            print(f"Scheduling reminder for {workout['user_id']} at {reminder_time_str}")
            aioschedule.every().day.at(reminder_time_str).do(
                lambda w=workout: asyncio.create_task(
                    send_reminder(bot, w['user_id'], f"Напоминание! Ваша тренировка назначена на {w['time']}.")
                )
            )
        else:
            print("Reminder time has passed, not scheduling.")

    print("All tasks scheduled.")

    # Запланировать напоминание
    aioschedule.every().day.at(reminder_time_str).do(lambda w=workout: asyncio.create_task(
        send_reminder(bot, w['user_id'], f"Напоминание! Ваша тренировка назначена на {w['time']}.")
    ))
handlers.py
import asyncio
import aioschedule
from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from utils import read_welcome_message, read_newbie_info, create_calendar, schedule_training_reminders, send_reminder
from db import save_user_selection, get_user_selection, get_todays_workouts
import logging
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher.filters import Command, Text
import re
from datetime import datetime, timedelta
import aioschedule
from aiogram import types, Dispatcher
from aiogram.dispatcher.filters import Command, Text
from utils import read_welcome_message, read_newbie_info, create_calendar, schedule_training_reminders, send_reminder
from db import save_user_selection, get_user_selection
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Form(StatesGroup):
    choosing_date = State()
    choosing_time = State()  # Это состояние теперь будет использоваться для ввода времени вручную
    entering_program = State()

async def send_welcome(message: types.Message):
    welcome_message = read_welcome_message()
    start_keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    start_keyboard.add(KeyboardButton('Я хочу начать меняться'))
    await message.answer(welcome_message, parse_mode='Markdown', reply_markup=start_keyboard)

async def process_start_button(message: types.Message):
    newbie_info = read_newbie_info()
    # Исправление синтаксиса для правильного вызова функции
    confirmation_keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    confirmation_keyboard.add(KeyboardButton('Всё понял'))
    await message.reply(newbie_info, reply_markup=confirmation_keyboard)

async def process_confirmation_button(message: types.Message):
    calendar_markup = create_calendar()
    await message.answer("Выберите дату:", reply_markup=calendar_markup)
    await Form.choosing_date.set()

async def calendar_callback_handler(callback_query: types.CallbackQuery, state: FSMContext):
    parts = callback_query.data.split('_')
    if len(parts) == 2 and parts[0] == 'day':
        _, date = parts
        year, month, day = date.split('-')
        full_date = f"{year}-{month}-{day}"
        logger.info(f"Handling day selection: {full_date}")
        await state.update_data(chosen_date=full_date)  # Сохраняем выбранную дату в состояние
        save_user_selection(callback_query.from_user.id, full_date, None)
        await callback_query.message.edit_text(
            f"Дата {full_date} выбрана. Теперь введите время тренировки в формате ЧЧ:ММ, например, 15:30.",
            reply_markup=None
        )
        await Form.choosing_time.set()
    else:
        logger.error(f"Unexpected action received or wrong data format: {parts}")
        await callback_query.answer("Некорректные данные. Пожалуйста, попробуйте снова.")
async def time_callback_handler(message: types.Message, state: FSMContext):
    # Проверяем формат времени
    time_match = re.match(r'^(\d{2}):(\d{2})$', message.text)
    if time_match:
        hours, minutes = int(time_match.group(1)), int(time_match.group(2))
        if not (0 <= hours < 24 and 0 <= minutes < 60):
            await message.answer("Время должно быть валидным (например, часы: 00-23, минуты: 00-59).")
            return
    else:
        await message.answer("Пожалуйста, введите время в правильном формате ЧЧ:ММ, например, 15:30.")
        return

    user_data = get_user_selection(message.from_user.id)
    if user_data and user_data[0]:  # Проверяем, что дата уже выбрана
        logger.info(f"Time selected: {message.text}, setting up workout program input")
        save_user_selection(message.from_user.id, user_data[0], message.text, None)  # Сохраняем выбранное время
        await message.answer(
            f"Вы выбрали время: {message.text}. Пожалуйста, теперь введите текст вашей программы тренировок.",
            reply_markup=ReplyKeyboardRemove()
        )
        await Form.entering_program.set()  # Устанавливаем состояние для ввода программы тренировок
    else:
        await message.answer("Пожалуйста, сначала выберите дату.")

async def safe_finish_state(state: FSMContext):
    try:
        data_exists = await state.get_data()
        if data_exists:
            await state.finish()
        else:
            logger.info("No state data to finish, might have been already cleaned up.")
    except KeyError as e:
        logger.error(f"KeyError when trying to finish state: {e}")
        # В случае ошибки, попытаемся безопасно очистить состояние без удаления данных
        await state.reset_state(with_data=False)
    except Exception as e:
        logger.error(f"An error occurred while finishing state: {e}")

async def process_workout_program(message: types.Message, state: FSMContext):
    user_data = get_user_selection(message.from_user.id)
    if user_data and user_data[0] and user_data[1]:  # Проверяем, что дата и время уже выбраны
        logger.info(f"Saving workout program for user: {message.from_user.id}")
        save_user_selection(message.from_user.id, user_data[0], user_data[1], message.text)
        await message.answer(
            "Программа тренировок сохранена. Вы можете выбрать другую дату.",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("Выбрать другую дату")]], resize_keyboard=True, one_time_keyboard=True
            )
        )
        await state.finish()  # Завершаем текущее состояние
    else:
        await message.answer("Пожалуйста, сначала выберите дату и время.")

async def send_calendar_again(message: types.Message, state: FSMContext):
    logger.info("Triggered send_calendar_again")
    calendar_markup = create_calendar()
    await message.answer("Выберите дату:", reply_markup=calendar_markup)
    await Form.choosing_date.set()  # Установка состояния для выбора даты, если это необходимо

async def schedule_training_reminders(bot):
    workouts = get_todays_workouts()
    now = datetime.now()

    for workout in workouts:
        workout_time = datetime.strptime(f"{workout['date']} {workout['time']}", "%Y-%m-%d %H:%M")
        reminder_time = workout_time - timedelta(minutes=1)
        reminder_time_str = reminder_time.strftime("%H:%M")

        if reminder_time > now:
            def schedule_task(w):
                asyncio.create_task(
                    send_reminder(bot, w['user_id'], f"Напоминание! Ваша тренировка назначена на {w['time']}.")
                )

            aioschedule.every().day.at(reminder_time_str).do(schedule_task, w=workout)
            print(f"Scheduling reminder for {workout['user_id']} at {reminder_time_str}")
async def send_reminder(bot, chat_id, message):
    print(f"Sending reminder to {chat_id}")
    await bot.send_message(chat_id, message)


def register_handlers(dp: Dispatcher):
    dp.register_message_handler(send_welcome, commands=['start'])
    dp.register_message_handler(process_start_button, Text(equals="Я хочу начать меняться"))
    dp.register_message_handler(process_confirmation_button, Text(equals="Всё понял"))
    dp.register_callback_query_handler(calendar_callback_handler, Text(startswith='day_'), state=Form.choosing_date)
    dp.register_message_handler(time_callback_handler, state=Form.choosing_time)
    dp.register_message_handler(process_workout_program, state=Form.entering_program)
    dp.register_message_handler(send_calendar_again, lambda message: message.text == "Выбрать другую дату", state='*')











6790788175:AAFylgos7EQjJWY1zPc6Vp9gw0o8RBjYupQ