import asyncio
from calendar import monthrange
from datetime import datetime, timedelta
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import aioschedule
from aiogram import Bot
from db import get_all_workouts
import sqlite3

def get_bot_text(key):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute("SELECT text FROM bot_texts WHERE key = ?", (key,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else ""

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
    try:
        await bot.send_message(chat_id, message)
    except Exception as e:
        print(f"Failed to send reminder to {chat_id}: {e}")

async def send_feedback_reminder(bot, chat_id, workout_time):
    try:
        feedback_markup = InlineKeyboardMarkup(row_width=3)
        feedback_markup.add(
            InlineKeyboardButton("Недовыполнил", callback_data="feedback_underdone"),
            InlineKeyboardButton("Выполнил", callback_data="feedback_done"),
            InlineKeyboardButton("Перевыполнил", callback_data="feedback_overdone")
        )
        await bot.send_message(chat_id,
                               f"Прошло 4 часа с момента вашей тренировки в {workout_time}. Выполнили ли вы свой план тренировки?",
                               reply_markup=feedback_markup)
    except Exception as e:
        print(f"Failed to send feedback reminder to {chat_id}: {e}")

async def schedule_task(delay, task, *args):
    await asyncio.sleep(delay)
    await task(*args)

async def schedule_reminders_for_workout(bot: Bot, workout: dict):
    now = datetime.now()
    workout_date = datetime.strptime(workout['date'], "%Y-%m-%d").date()
    workout_time = datetime.strptime(workout['time'], "%H:%M").time()
    workout_datetime = datetime.combine(workout_date, workout_time)
    reminder_time_2hours = workout_datetime - timedelta(hours=2)
    feedback_time = workout_datetime + timedelta(hours=4)

    if workout_datetime > now:
        if reminder_time_2hours > now:
            delay = (reminder_time_2hours - now).total_seconds()
            asyncio.create_task(schedule_task(delay, send_reminder, bot, workout['user_id'], f"Напоминание! Ваша тренировка назначена на {workout['time']}."))

        if feedback_time > now:
            delay = (feedback_time - now).total_seconds()
            asyncio.create_task(schedule_task(delay, send_feedback_reminder, bot, workout['user_id'], workout['time']))

async def schedule_future_reminders(bot: Bot):
    workouts = get_all_workouts()
    for workout in workouts:
        workout_dict = {
            'user_id': workout[0],
            'date': workout[1],
            'time': workout[2]
        }
        await schedule_reminders_for_workout(bot, workout_dict)
