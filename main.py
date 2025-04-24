# --- START OF FILE bot.py ---

import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton
from environs import Env

env = Env()
env.read_env() # Пытается прочитать .env для локальной разработки

# Пример получения токена в bot.py
# bot_token = os.getenv("API_TOKEN") -> заменяем на:
bot_token = env.str("API_TOKEN")
# Импортируем роутеры и общие хендлеры
from handlers import bus, trolleybus, favorites, common_handlers
import utils # Нужен для инициализации данных при старте

# Настройка логирования для отладки
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')

# --- Инициализация ---
if not bot_token:
    logging.critical("API_TOKEN environment variable not set!")
    raise ValueError("Необходимо установить переменную окружения API_TOKEN")

bot = Bot(token=bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# --- Главное меню ---
main_menu_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text=f"{common_handlers.TRANSPORT_CONFIG[common_handlers.TYPE_BUS]['emoji']} {common_handlers.TRANSPORT_CONFIG[common_handlers.TYPE_BUS]['name_plural']}"),
            KeyboardButton(text=f"{common_handlers.TRANSPORT_CONFIG[common_handlers.TYPE_TROLLEYBUS]['emoji']} {common_handlers.TRANSPORT_CONFIG[common_handlers.TYPE_TROLLEYBUS]['name_plural']}")
        ],
         [KeyboardButton(text="⭐ Избранное")]
    ],
    resize_keyboard=True,
    input_field_placeholder="Выберите тип транспорта или Избранное"
)


# --- Общие обработчики (Старт, Назад) ---
# Регистрируем первыми на dp
@dp.message(F.text == "/start")
async def start_command_handler(message: Message):
    """Обработчик команды /start"""
    logging.info(f"User {message.from_user.id} ({message.from_user.username}) triggered /start")
    await message.answer(
        f"👋 Добро пожаловать, {message.from_user.first_name}!\n"
        "Я помогу вам узнать расписание общественного транспорта.",
        reply_markup=main_menu_keyboard
    )

@dp.message(F.text == "🔙 На главную")
async def back_to_main_menu_handler(message: Message):
    """Обработчик кнопки 'На главную' из ReplyKeyboard"""
    logging.info(f"User {message.from_user.id} ({message.from_user.username}) requested main menu via ReplyKeyboard")
    await message.answer("Вы вернулись в главное меню.", reply_markup=main_menu_keyboard)

@dp.callback_query(F.data == "back_to_main")
async def back_to_main_menu_inline_handler(callback: CallbackQuery):
    """Обработчик инлайн-кнопки 'На главную'"""
    logging.info(f"User {callback.from_user.id} ({callback.from_user.username}) requested main menu via InlineKeyboard")
    await callback.answer()
    if callback.message:
        await callback.message.answer("Вы вернулись в главное меню.", reply_markup=main_menu_keyboard)
        try:
             await callback.message.edit_reply_markup(reply_markup=None)
        except Exception as e:
            logging.warning(f"Could not edit reply markup on back_to_main for user {callback.from_user.id}: {e}")
            pass
    else:
        await bot.send_message(callback.from_user.id, "Вы вернулись в главное меню.", reply_markup=main_menu_keyboard)


# --- Подключаем роутеры ---
# Диспетчер будет проверять их в этом порядке
dp.include_router(bus.router)           # Проверит F.text == "🚌 Автобусы" здесь
dp.include_router(trolleybus.router)    # Проверит F.text == "🚎 Троллейбусы" здесь
dp.include_router(favorites.router)     # Проверит F.text == "⭐ Избранное" здесь


# --- Функция для периодического обновления данных (пример) ---
async def scheduled_reload(interval_seconds: int):
    """Периодически вызывает принудительную перезагрузку кэша."""
    while True:
        await asyncio.sleep(interval_seconds)
        logging.info(f"Scheduled task: Reloading schedule data...")
        try:
            await asyncio.to_thread(utils.force_reload_all_schedules)
            logging.info("Scheduled task: Schedule data reloaded successfully.")
        except Exception as e:
            logging.error(f"Scheduled task: Error reloading schedules: {e}", exc_info=True)

# --- Запуск бота ---
async def main():
    logging.info("Initializing schedule data...")
    try:
        utils.getBusSchedule()
        utils.getTrolleybusSchedule()
        logging.info("Schedule data initialized successfully.")
    except Exception as e:
        logging.error(f"Failed to initialize schedule data on startup: {e}", exc_info=True)
        # raise # Раскомментировать, если без данных бот работать не может

    # Запуск фоновой задачи обновления - раскомментируйте при необходимости
    # reload_interval = 7 * 24 * 60 * 60
    # logging.info(f"Scheduling data reload every {reload_interval} seconds.")
    # asyncio.create_task(scheduled_reload(reload_interval))

    logging.info("Starting bot polling...")
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        # Указываем allowed_updates для эффективности
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as e:
        logging.critical(f"Polling failed: {e}", exc_info=True)
    finally:
        logging.info("Closing bot session.")
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped by user.")
    except Exception as e:
        logging.critical(f"Critical error in main execution: {e}", exc_info=True)

# --- END OF FILE bot.py ---