import sqlite3
from datetime import datetime

def create_connection():
    return sqlite3.connect('bot.db')

def setup_db():
    conn = create_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_selections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            date TEXT,
            time TEXT,
            workout_program TEXT,
            feedback TEXT,
            completed INTEGER DEFAULT 0
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS bot_texts (
            key TEXT PRIMARY KEY,
            text TEXT
        )
    ''')
    conn.commit()
    conn.close()
    add_column_if_not_exists()

def add_column_if_not_exists():
    conn = create_connection()
    c = conn.cursor()
    try:
        c.execute("ALTER TABLE user_selections ADD COLUMN completed INTEGER DEFAULT 0")
    except sqlite3.OperationalError as e:
        if "duplicate column name" not in str(e):
            raise
    conn.commit()
    conn.close()

def save_user_selection(user_id, date, time, workout_program=None):
    conn = create_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO user_selections (user_id, date, time, workout_program, completed)
        VALUES (?, ?, ?, ?, 0)
    """, (user_id, date, time, workout_program))
    conn.commit()
    conn.close()

def update_user_selection(user_id, old_date, old_time, new_date, new_time, workout_program):
    conn = create_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE user_selections
        SET date = ?, time = ?, workout_program = ?
        WHERE user_id = ? AND date = ? AND time = ?
    """, (new_date, new_time, workout_program, user_id, old_date, old_time))
    conn.commit()
    conn.close()

def save_feedback(user_id, date, time, feedback):
    conn = create_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE user_selections
        SET feedback = ?, completed = 1
        WHERE user_id = ? AND date = ? AND time = ?
    """, (feedback, user_id, date, time))
    conn.commit()
    conn.close()

def get_user_progress(user_id, start_date):
    conn = create_connection()
    c = conn.cursor()
    c.execute("SELECT date, time, workout_program, feedback FROM user_selections WHERE user_id = ? AND date >= ? AND completed = 1", (user_id, start_date))
    result = c.fetchall()
    conn.close()
    return result

def get_user_selection(user_id):
    conn = create_connection()
    c = conn.cursor()
    c.execute("SELECT date, time, workout_program, feedback FROM user_selections WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result

def get_todays_workouts():
    today = datetime.now().strftime("%Y-%m-%d")
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, date, time FROM user_selections WHERE date = ?", (today,))
    workouts = [{'user_id': row[0], 'date': row[1], 'time': row[2]} for row in cursor.fetchall()]
    conn.close()
    return workouts

def get_all_workouts():
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, date, time FROM user_selections")
    workouts = cursor.fetchall()
    conn.close()
    return workouts  # Должно возвращать список кортежей

def get_future_workouts(user_id):
    today = datetime.now().strftime("%Y-%m-%d")
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT date, time, workout_program FROM user_selections WHERE user_id = ? AND date >= ? ORDER BY date, time", (user_id, today))
    workouts = cursor.fetchall()
    conn.close()
    return workouts

def delete_workout(user_id, date, time):
    conn = create_connection()
    c = conn.cursor()
    c.execute("""
        DELETE FROM user_selections
        WHERE user_id = ? AND date = ? AND time = ?
    """, (user_id, date, time))
    conn.commit()
    conn.close()

def get_bot_text(key):
    conn = create_connection()
    c = conn.cursor()
    c.execute("SELECT text FROM bot_texts WHERE key = ?", (key,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else ""

def initialize_texts():
    conn = create_connection()
    c = conn.cursor()
    texts = {
        "welcome_message": "Привет! Я бот FitCalendar, который поможет тебе планировать и отслеживать свои тренировки! 🏋️‍♂️\n\nЯ помогу тебе не забыть о предстоящих тренировках и буду напоминать об этом. Давай начнем!\n\nНажми на кнопку ниже, чтобы узнать больше.",
        "rules_message": "Правила использования бота 📋:\n\n1️⃣ Следи за сном:\n   - Убедись, что у тебя достаточно сна для восстановления 🛌.\n\n2️⃣ Питайся правильно:\n   - Здоровое питание важно для достижения результатов 🍎.\n\n3️⃣ Пей достаточно воды:\n   - Гидратация важна для поддержания энергии и восстановления 💧.\n\n4️⃣ Разминайся перед тренировкой:\n   - Разминка помогает избежать травм и улучшить производительность 🤸.\n\n5️⃣ Держи позитивный настрой:\n   - Мотивация и позитивное мышление помогут достигать целей 💪.\n\nСледуй этим простым правилам для достижения максимального результата!",
        "instructions_message": "Вот как работает бот: \n\n1️⃣ Выберите дату и время тренировки 📅🕒.\n\n2️⃣ Введите программу тренировки 🏋️‍♀️.\n\n3️⃣ Получайте напоминания о тренировке 📬.\n\n4️⃣ После тренировки предоставьте обратную связь 📝.\n\n5️⃣ Просматривайте свой прогресс с помощью кнопки \"Мой прогресс\"📊.\n\n6️⃣ Редактируйте и удаляйте ненужные тренировки с помощью кнопки \"Расписание\"✏️🗑️.\n\n👇 Если все еще есть вопросы или хочешь подробнее посмотреть функционал бота, тогда нажимай \"Не понял, давай поподробнее\", а если ты все понял, тогда приятного использования!",
        "detailed_instructions_message": "Подробная инструкция по использованию бота 📘:\n\n1️⃣ Добавить новую тренировку:\n   - Нажми кнопку \"Добавить новую тренировку\" в главном меню.\n   - Выбери дату тренировки 📅 с помощью календаря.\n   - Укажи время тренировки 🕒 в формате ЧЧ:ММ (например, 08:30 или 21:44).\n\n2️⃣ Заполнение программы тренировки:\n   - Введи текст программы тренировки (например, \"Бег 5 км\" или \"Силовая тренировка 1 час\").\n\n3️⃣ Напоминания о тренировке:\n   - Получишь два напоминания: за 2 часа и за 1 минуту до тренировки 🔔.\n\n4️⃣ Обратная связь после тренировки:\n   - После тренировки бот попросит тебя оценить выполнение программы: \"Недовыполнил\", \"Выполнил\" или \"Перевыполнил\" 🗣️.\n   - Введи дополнительные комментарии, если выберешь \"Недовыполнил\" или \"Перевыполнил\".\n\n5️⃣ Просмотр прогресса:\n   - Нажми \"Мой прогресс\" в главном меню.\n  - Выбери период (неделя, месяц, год) для отображения статистики 📊.\n\n6️⃣ Редактирование и удаление тренировок:\n   - Нажми \"Расписание\" в главном меню, чтобы увидеть запланированные тренировки.\n   - Используй кнопки \"Изменить\" или \"Удалить\" для управления тренировками ✏️🗑️.\n\nНажми \"Вот теперь мне все понятно\" для начала работы 👇.",
    }
    for key, text in texts.items():
        c.execute("""
            INSERT OR REPLACE INTO bot_texts (key, text)
            VALUES (?, ?)
        """, (key, text))
    conn.commit()
    conn.close()
