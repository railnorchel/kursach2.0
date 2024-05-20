import asyncio
import aioschedule
from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from utils import create_calendar, send_reminder, send_feedback_reminder, schedule_reminders_for_workout, get_bot_text
from db import save_user_selection, get_user_selection, get_todays_workouts, save_feedback, get_user_progress, \
    get_future_workouts, delete_workout, update_user_selection
import logging
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, CallbackQuery, InlineKeyboardMarkup, \
    InlineKeyboardButton, ReplyKeyboardRemove, Message
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher.filters import Command, Text
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Form(StatesGroup):
    choosing_date = State()
    choosing_time = State()
    entering_program = State()
    entering_feedback_details = State()


def translate_feedback(feedback):
    translations = {
        "underdone": "Недовыполнил",
        "done": "Выполнил",
        "overdone": "Перевыполнил"
    }
    return translations.get(feedback, feedback)


async def send_welcome(message: types.Message):
    welcome_message = get_bot_text("welcome_message")
    start_keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    start_keyboard.add(KeyboardButton('Понял, а правила тут есть?'))
    await message.answer(welcome_message, parse_mode='Markdown', reply_markup=start_keyboard)


async def process_start_button(message: types.Message):
    rules_message = get_bot_text("rules_message")
    confirmation_keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    confirmation_keyboard.add(KeyboardButton('Ясно, а как работает бот?'))
    await message.reply(rules_message, reply_markup=confirmation_keyboard)


async def process_confirmation_button(message: types.Message):
    instructions_message = get_bot_text("instructions_message")
    instructions_keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    instructions_keyboard.add(KeyboardButton('Не понял, давай поподробнее'))
    instructions_keyboard.add(KeyboardButton('Давай уже приступим!'))
    await message.reply(instructions_message, reply_markup=instructions_keyboard)


async def process_detailed_instructions_button(message: types.Message):
    detailed_instructions_message = get_bot_text("detailed_instructions_message")
    detailed_instructions_keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    detailed_instructions_keyboard.add(KeyboardButton('Вот теперь мне все понятно'))
    await message.reply(detailed_instructions_message, reply_markup=detailed_instructions_keyboard)


async def process_begin_button(message: types.Message):
    main_menu_keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    main_menu_keyboard.add(KeyboardButton("Добавить новую тренировку"),
                           KeyboardButton("Мой прогресс"),
                           KeyboardButton("Расписание"),
                           KeyboardButton("Помощь"))
    await message.answer("Вы в главном меню. Выберите действие:", reply_markup=main_menu_keyboard)


async def calendar_callback_handler(callback_query: CallbackQuery, state: FSMContext):
    parts = callback_query.data.split('_')
    if len(parts) == 2 and parts[0] == 'day':
        date = parts[1]
        chosen_date = datetime.strptime(date, "%Y-%m-%d").date()
        if chosen_date < datetime.now().date():
            await callback_query.answer("Данная дата уже прошла. Пожалуйста, выберите корректную дату.",
                                        show_alert=True)
        else:
            await state.update_data(chosen_date=date)
            await callback_query.message.delete_reply_markup()  # Удаление инлайн-клавиатуры
            back_keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard = True)
            back_keyboard.add(KeyboardButton('Назад'))
            msg = await callback_query.message.answer(
                f"Вы выбрали {date}\nТеперь введите время тренировки в формате ЧЧ:ММ.\nНапример, 08:30 или 21:44.",
                reply_markup=back_keyboard)
            await state.update_data(last_message_id=msg.message_id)
            await Form.choosing_time.set()
    else:
        await callback_query.answer("Некорректные данные.")


async def time_callback_handler(message: Message, state: FSMContext):
    user_data = await state.get_data()
    chosen_date = user_data.get('chosen_date')

    if message.text == "Назад":
        last_message_id = user_data.get('last_message_id')
        if last_message_id:
            await message.bot.delete_message(message.chat.id, last_message_id)
        calendar_markup = create_calendar()
        msg = await message.answer("Выберите дату: (Отображается текущий месяц и год)", reply_markup=calendar_markup)
        await state.update_data(last_message_id=msg.message_id)
        await Form.choosing_date.set()
        return

    time_text = message.text
    if time_text == "Добавить новую тренировку":
        await send_calendar_again(message, state)
        return

    # Validate time format
    try:
        chosen_datetime = datetime.strptime(f"{chosen_date} {time_text}", "%Y-%m-%d %H:%M")
        if chosen_datetime < datetime.now():
            raise ValueError("Time is in the past.")
    except ValueError:
        msg = await message.answer(
            "Некорректный формат времени. Пожалуйста, введите время в формате ЧЧ:ММ.\nНапример, 08:30 или 21:44.")
        await state.update_data(last_message_id=msg.message_id)
        return

    await state.update_data(chosen_time=time_text)
    back_keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard = True)
    back_keyboard.add(KeyboardButton('Назад'))
    msg = await message.answer(
        "Введите текст программы тренировок.\n\nНапример:\n- Бег 5 км\n- Силовая тренировка 1 час\n- Йога 30 минут",
        reply_markup=back_keyboard)
    await state.update_data(last_message_id=msg.message_id)
    await Form.entering_program.set()


async def program_callback_handler(message: Message, state: FSMContext):
    user_data = await state.get_data()

    if message.text == "Назад":
        last_message_id = user_data.get('last_message_id')
        if last_message_id:
            await message.bot.delete_message(message.chat.id, last_message_id)
        date = user_data.get('chosen_date')
        msg = await message.answer(
            f"Вы выбрали {date}\nТеперь введите время тренировки в формате ЧЧ:ММ.\нНапример, 08:30 или 21:44.",
            reply_markup=ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard = True).add(
            KeyboardButton('Назад')))
        await state.update_data(last_message_id=msg.message_id)
        await Form.choosing_time.set()
        return

    program_text = message.text
    date = user_data.get('chosen_date')
    time = user_data.get('chosen_time')

    if not (date and time):
        msg = await message.answer("Сначала выберите дату и время.")
        await state.update_data(last_message_id=msg.message_id)
        return

    if program_text == "Добавить новую тренировку":
        await send_calendar_again(message, state)
        return

    editing_workout = user_data.get('editing_workout')
    if editing_workout:
        old_date, old_time = editing_workout.split('_')
        update_user_selection(message.from_user.id, old_date, old_time, date, time, program_text)
        await state.update_data(editing_workout=None)
    else:
        save_user_selection(message.from_user.id, date, time, program_text)

    workout = {'user_id': message.from_user.id, 'date': date, 'time': time}
    await schedule_reminders_for_workout(message.bot, workout)

    reply_markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard = True)
    reply_markup.add(KeyboardButton("Добавить новую тренировку"), KeyboardButton("Мой прогресс"),
                     KeyboardButton("Расписание"), KeyboardButton("Помощь"))
    await message.answer("Программа тренировок сохранена.", reply_markup=reply_markup)
    await state.reset_state(with_data=False)


async def send_calendar_again(message: types.Message, state: FSMContext):
    await state.reset_state(with_data=True)
    calendar_markup = create_calendar()
    await message.answer("Выберите дату: (Отображается текущий месяц и год)", reply_markup=calendar_markup)
    await Form.choosing_date.set()


async def start_calendar(message: types.Message, state: FSMContext):
    await Form.choosing_date.set()
    calendar_markup = create_calendar()
    await message.answer("Выберите дату: (Отображается текущий месяц и год)", reply_markup=calendar_markup)


async def date_chosen(callback_query: types.CallbackQuery, state: FSMContext):
    await Form.choosing_time.set()
    await callback_query.message.answer("Введите время в формате ЧЧ:ММ.")


async def time_chosen(message: types.Message, state: FSMContext):
    await Form.entering_program.set()
    await state.update_data(chosen_time=message.text)
    await message.answer(
        "Введите текст вашей программы тренировок.\n\nНапример:\n- Бег 5 км\n- Силовая тренировка 1 час\n- Йога 30 минут")


async def program_entered(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    save_user_selection(message.from_user.id, user_data['chosen_date'], user_data['chosen_time'], message.text)
    await state.finish()
    await message.answer("Ваши данные сохранены.")


async def choose_new_date(message: types.Message, state: FSMContext):
    await state.reset_state()
    await start_calendar(message, state)


async def process_feedback(callback_query: CallbackQuery, state: FSMContext):
    feedback = callback_query.data.split('_')[1]
    user_id = callback_query.from_user.id
    user_data = await state.get_data()
    date = user_data.get('chosen_date')
    time = user_data.get('chosen_time')
    await state.update_data(feedback=feedback)

    # Удаление инлайн-клавиатуры после выбора
    await callback_query.message.edit_reply_markup(reply_markup=None)

    if feedback == 'underdone' or feedback == 'overdone':
        await callback_query.message.answer("Сообщите, что вы успели сделать за сегодня.")
        await Form.entering_feedback_details.set()
    elif feedback == 'done':
        save_feedback(user_id, date, time, feedback)
        await callback_query.message.answer("Молодец!")
        await state.finish()


async def feedback_details(message: types.Message, state: FSMContext):
    details = message.text
    user_data = await state.get_data()
    feedback = user_data.get('feedback')
    date = user_data.get('chosen_date')
    time = user_data.get('chosen_time')

    save_feedback(message.from_user.id, date, time, f"{translate_feedback(feedback)}: {details}")
    await send_message_with_retry(message, "Спасибо за вашу обратную связь!")
    await state.finish()


async def send_message_with_retry(message: types.Message, text: str, retry_count: int = 3):
    for attempt in range(retry_count):
        try:
            await message.answer(text)
            break
        except Exception as e:
            if attempt < retry_count - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
            else:
                logger.error(f"Failed to send message after {retry_count} attempts: {e}")


async def show_progress_options(message: types.Message):
    progress_keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard = True)
    progress_keyboard.add(KeyboardButton("За неделю"), KeyboardButton("За месяц"), KeyboardButton("За год"),
                          KeyboardButton("Выход"))
    await message.answer("Выберите период для отображения прогресса:", reply_markup=progress_keyboard)


async def show_progress(message: types.Message, period: str):
    user_id = message.from_user.id
    now = datetime.now()

    if period == 'week':
        start_date = now - timedelta(weeks=1)
        period_name = "неделю"
    elif period == 'month':
        start_date = now - timedelta(days=30)  # приблизительно
        period_name = "месяц"
    elif period == 'year':
        start_date = now - timedelta(days=365)
        period_name = "год"
    else:
        await send_message_with_retry(message, "Некорректный период.")
        return

    progress_data = get_user_progress(user_id, start_date)

    if not progress_data:
        await send_message_with_retry(message, f"Нет данных о прогрессе за {period_name}.")
        return

    progress_message = f"Ваш прогресс за {period_name}:\n"
    for entry in progress_data:
        date, time, workout_program, feedback = entry
        progress_message += f"\nДата: {date}\nВремя: {time}\nПрограмма: {workout_program}\n"
        if feedback:
            translated_feedback = translate_feedback(feedback)
            progress_message += f"Обратная связь: {translated_feedback}\n"
        progress_message += "-" * 20

    await send_message_with_retry(message, progress_message)


async def handle_exit_button(message: types.Message):
    start_keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard = True)
    start_keyboard.add(KeyboardButton("Добавить новую тренировку"), KeyboardButton("Мой прогресс"),
                       KeyboardButton("Расписание"), KeyboardButton("Помощь"))
    await message.answer("Вы вернулись в главное меню.", reply_markup=start_keyboard)


async def show_schedule(message: types.Message):
    user_id = message.from_user.id
    future_workouts = get_future_workouts(user_id)

    if not future_workouts:
        await message.answer("У вас нет запланированных тренировок.")
        return

    now = datetime.now()
    for workout in future_workouts:
        date_str, time_str, workout_program = workout
        workout_date = datetime.strptime(date_str, "%Y-%m-%d").date()  # Исправленный формат даты
        workout_time = datetime.strptime(time_str, "%H:%M").time()
        workout_datetime = datetime.combine(workout_date, workout_time)

        if workout_datetime >= now:
            workout_message = f"Дата: {date_str}\nВремя: {time_str}\nПрограмма: {workout_program}"
            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(
                InlineKeyboardButton("Удалить", callback_data=f"delete_{date_str}_{time_str}"),
                InlineKeyboardButton("Изменить", callback_data=f"edit_{date_str}_{time_str}")
            )
            await message.answer(workout_message, reply_markup=markup)

    await message.answer("Чтобы выйти, нажмите кнопку ниже.",
                         reply_markup=ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard = True).add(
        KeyboardButton('Выход')))

async def handle_delete_workout(callback_query: CallbackQuery):
        data = callback_query.data.split('_')
        date, time = data[1], data[2]
        user_id = callback_query.from_user.id

        delete_workout(user_id, date, time)

        # Удаление инлайн-клавиатуры после удаления тренировки
        if callback_query.message.reply_markup:
            await callback_query.message.edit_reply_markup(reply_markup=None)

        await callback_query.message.edit_text("Тренировка удалена.")

        # Отменяем все напоминания связанные с удаленной тренировкой
        aioschedule.clear(f"{user_id}_{date}_{time}")

async def handle_edit_workout(callback_query: CallbackQuery, state: FSMContext):
        data = callback_query.data.split('_')
        date, time = data[1], data[2]
        user_id = callback_query.from_user.id

        await state.update_data(editing_workout=f"{date}_{time}")
        await callback_query.message.edit_text("Выберите новую дату для тренировки:")

        calendar_markup = create_calendar()
        await callback_query.message.answer("Выберите дату:", reply_markup=calendar_markup)
        await Form.choosing_date.set()

async def help_command(message: types.Message):
        detailed_instructions_message = get_bot_text("detailed_instructions_message")
        detailed_instructions_keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard = True)
        detailed_instructions_keyboard.add(KeyboardButton('Вот теперь мне все понятно'))
        await message.reply(detailed_instructions_message, reply_markup=detailed_instructions_keyboard)

def register_handlers(dp: Dispatcher):
        dp.register_message_handler(send_welcome, commands=['start'])
        dp.register_message_handler(process_start_button, Text(equals="Понял, а правила тут есть?"))
        dp.register_message_handler(process_confirmation_button, Text(equals="Ясно, а как работает бот?"))
        dp.register_message_handler(process_detailed_instructions_button, Text(equals="Не понял, давай поподробнее"))
        dp.register_message_handler(process_begin_button,
                                    Text(equals="Давай уже приступим!"))  # Обработчик для "Давай уже приступим!"
        dp.register_message_handler(process_begin_button, Text(
            equals="Вот теперь мне все понятно"))  # Обработчик для "Вот теперь мне все понятно"
        dp.register_message_handler(help_command, Text(equals="Помощь"))  # Обработчик для команды "Помощь"
        dp.register_message_handler(show_progress_options, Text(equals="Мой прогресс"), state='*')
        dp.register_message_handler(lambda message: show_progress(message, 'week'), Text(equals="За неделю"), state='*')
        dp.register_message_handler(lambda message: show_progress(message, 'month'), Text(equals="За месяц"), state='*')
        dp.register_message_handler(lambda message: show_progress(message, 'year'), Text(equals="За год"), state='*')
        dp.register_message_handler(handle_exit_button, Text(equals="Выход"), state='*')
        dp.register_message_handler(show_schedule, Text(equals="Расписание"), state='*')
        dp.register_callback_query_handler(handle_delete_workout, Text(startswith='delete_'), state='*')
        dp.register_callback_query_handler(handle_edit_workout, Text(startswith='edit_'), state='*')
        dp.register_callback_query_handler(calendar_callback_handler, Text(startswith='day_'), state=Form.choosing_date)
        dp.register_message_handler(time_callback_handler, state=Form.choosing_time)
        dp.register_message_handler(program_callback_handler, state=Form.entering_program)
        dp.register_message_handler(send_calendar_again, lambda message: message.text == "Добавить новую тренировку",
                                    state='*')
        dp.register_callback_query_handler(process_feedback, Text(startswith='feedback_'), state='*')
        dp.register_message_handler(feedback_details, state=Form.entering_feedback_details)
