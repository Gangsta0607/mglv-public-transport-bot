# --- START OF FILE bus.py ---

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
import utils
# Импортируем общие хендлеры и константы
from handlers import common_handlers
import logging

router = Router()
TRANSPORT_TYPE = common_handlers.TYPE_BUS
CONFIG = common_handlers.TRANSPORT_CONFIG[TRANSPORT_TYPE]

# Загружаем данные при старте (с использованием кэша из utils)
BUS_DATA = utils.getBusSchedule()

# Оставляем ReplyKeyboard здесь, т.к. она специфична для входа в раздел
bus_menu_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="⭐ Избранное"), # Текст кнопки общий
            KeyboardButton(text="🔙 На главную") # Текст кнопки общий
        ],
    ],
    resize_keyboard=True,
)

@router.message(F.text == f"{CONFIG['emoji']} {CONFIG['name_plural']}")
async def start_bus_handler(message: Message):
    """Отображает список автобусов."""
    # Обновляем данные на случай, если они изменились с момента старта
    # Это не перезагрузит парсер, если кэш валиден
    bus_data = utils.getBusSchedule()
    if not bus_data:
         await message.answer(f"Не удалось загрузить расписание {CONFIG['name_plural']}. Попробуйте позже.")
         return

    kb = InlineKeyboardBuilder()
    msg_text = f"<b>Список {CONFIG['name_plural']}:</b>\n"
    # Сортируем номера автобусов (если они числовые или как строки)
    sorted_numbers = sorted(bus_data.keys(), key=lambda x: (0, int(x)) if x.isdigit() else (1, x))

    for number in sorted_numbers:
        bus = bus_data[number]
        # Используем get для безопасного доступа к полям
        route_name = bus.get('route_name', 'Нет данных о маршруте')
        msg_text += f"<b>{CONFIG['emoji']} {CONFIG['name_singular']} №{bus.get('number', number)}</b> — <code>{route_name}</code>\n"
        # Используем callback_prefix из конфига
        kb.button(text=f"{CONFIG['emoji']} №{number}", callback_data=f"{CONFIG['callback_prefix']}_{number}")

    kb.adjust(3)
    await message.answer(f"Меню '{CONFIG['name_plural']}'", reply_markup=bus_menu_keyboard)

    # Разбиваем сообщение, если оно слишком длинное
    if len(msg_text) > 4096:
        for i in range(0, len(msg_text), 4096):
             # Отправляем кнопки только с последней частью
             reply_markup = kb.as_markup() if i + 4096 >= len(msg_text) else None
             await message.answer(msg_text[i:i+4096], reply_markup=reply_markup)
    else:
       await message.answer(msg_text, reply_markup=kb.as_markup())


# --- Обработчики CallbackQuery ---

@router.callback_query(F.data.startswith(f"{CONFIG['callback_prefix']}_"))
async def select_bus_handler(callback: CallbackQuery):
    """Выбор конкретного автобуса -> показать направления."""
    try:
        number = callback.data.split("_")[1]
    except IndexError:
        await callback.answer("Ошибка: Некорректный callback data.", show_alert=True)
        return
    bus_data = utils.getBusSchedule() # Получаем актуальные данные
    await common_handlers.show_directions(callback, TRANSPORT_TYPE, bus_data, number)

@router.callback_query(F.data.startswith(f"route_{CONFIG['callback_prefix']}_"))
async def select_route_handler(callback: CallbackQuery):
    """Выбор направления -> показать остановки."""
    try:
        parts = callback.data.split("_")
        number = parts[2]
        route_idx = int(parts[3])
    except (IndexError, ValueError):
        await callback.answer("Ошибка: Некорректный callback data.", show_alert=True)
        return
    bus_data = utils.getBusSchedule()
    # Вызываем show_stops, который теперь добавит day_type в колбэк остановки
    await common_handlers.show_stops(callback, TRANSPORT_TYPE, bus_data, number, route_idx)

# Изменяем обработчик остановки, чтобы извлечь day_type
@router.callback_query(F.data.startswith(f"stop_{CONFIG['callback_prefix']}_"))
async def show_schedule_handler(callback: CallbackQuery):
    """Выбор остановки -> показать расписание."""
    try:
        # stop_bus_NUMBER_ROUTEIDX_STOPIDX_DAYTYPE
        parts = callback.data.split("_")
        if len(parts) != 6: raise ValueError("Incorrect callback data parts")
        number = parts[2]
        route_idx = int(parts[3])
        stop_idx = int(parts[4])
        day_type = parts[5] # Получаем тип дня из колбэка
        if day_type not in [common_handlers.DAY_WD, common_handlers.DAY_WE]:
             raise ValueError(f"Invalid day_type: {day_type}")

    except (IndexError, ValueError) as e:
        logging.warning(f"Invalid stop callback data: {callback.data} - {e}")
        await callback.answer("Ошибка: Некорректный формат данных остановки.", show_alert=True)
        return

    bus_data = utils.getBusSchedule()
    # Передаем day_type в show_schedule_details
    await common_handlers.show_schedule_details(
        callback, TRANSPORT_TYPE, bus_data, number, route_idx, stop_idx, day_type=day_type, is_from_favorites=False
    )

# --- Обработчик для переключения дня ---
@router.callback_query(F.data.startswith(f"{CONFIG['toggle_day_prefix']}_"))
async def toggle_day_handler(callback: CallbackQuery):
    """Переключает отображение между буднями и выходными."""
    try:
        # toggle_day_bus_NUMBER_ROUTEIDX_STOPIDX_TARGETDAYTYPE_ISFAV
        # Части: 0       1   2  3       4         5         6             7
        parts = callback.data.split("_")
        # --- ИСПРАВЛЕНО: Проверяем на 8 частей ---
        if len(parts) != 8: raise ValueError("Incorrect toggle callback data parts")

        number = parts[3]
        route_idx = int(parts[4])
        stop_idx = int(parts[5])
        target_day_type = parts[6]
        # --- ИСПРАВЛЕНО: Правильный индекс для is_fav ---
        is_fav_int = int(parts[7])
        is_from_favorites = bool(is_fav_int)

        if target_day_type not in [common_handlers.DAY_WD, common_handlers.DAY_WE]:
             raise ValueError(f"Invalid target_day_type: {target_day_type}")

    except (IndexError, ValueError) as e:
        logging.warning(f"Invalid toggle callback data: {callback.data} - {e}")
        await callback.answer("Ошибка: Некорректный формат данных для переключения.", show_alert=True)
        return

    bus_data = utils.getBusSchedule()
    # Вызываем ту же функцию, но с новым day_type и сохраняем is_from_favorites
    await common_handlers.show_schedule_details(
        callback, TRANSPORT_TYPE, bus_data, number, route_idx, stop_idx, day_type=target_day_type, is_from_favorites=is_from_favorites
    )


# --- Обработчики кнопок "Назад" ---
@router.callback_query(F.data == f"back_to_{TRANSPORT_TYPE}_list")
async def back_to_list_handler(callback: CallbackQuery):
    """Возврат к списку автобусов (вызывает start_bus_handler)."""
    await common_handlers.back_to_transport_list(callback, TRANSPORT_TYPE, start_bus_handler)

# --- Dummy callback handler (если используется) ---
@router.callback_query(F.data == "dummy_in_favorites")
async def handle_dummy_fav_callback(callback: CallbackQuery):
     await common_handlers.handle_dummy_callback(callback)

# --- END OF FILE bus.py ---