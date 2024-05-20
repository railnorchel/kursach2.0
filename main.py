import asyncio
from aiogram import Bot, Dispatcher
from aiogram.utils import executor
from handlers import register_handlers
from db import setup_db, initialize_texts
import aioschedule
from safe_storage import SafeMemoryStorage
from utils import schedule_future_reminders

API_TOKEN = '6790788175:AAFylgos7EQjJWY1zPc6Vp9gw0o8RBjYupQ'

bot = Bot(token=API_TOKEN)
storage = SafeMemoryStorage()
dp = Dispatcher(bot, storage=storage)

def setup_dispatcher():
    setup_db()
    initialize_texts()
    register_handlers(dp)

async def scheduler():
    while True:
        await aioschedule.run_pending()
        await asyncio.sleep(1)

async def on_startup(dispatcher):
    await schedule_future_reminders(bot)

def main():
    setup_dispatcher()
    loop = asyncio.get_event_loop()
    loop.create_task(scheduler())
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)

if __name__ == '__main__':
    main()
