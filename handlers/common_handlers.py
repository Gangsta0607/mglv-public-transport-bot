# --- START OF FILE common_handlers.py ---

import datetime
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
import logging # Добавим логирование
import utils # Импортируем utils для проверки избранного

# --- Константы для типов транспорта и дней ---
TYPE_BUS = "bus"
TYPE_TROLLEYBUS = "trolleybus"
DAY_WD = "wd" # Weekday
DAY_WE = "we" # Weekend

TRANSPORT_CONFIG = {
    TYPE_BUS: {
        "emoji": "🚌",
        "name_singular": "Автобус",
        "name_plural": "Автобусы",
        "callback_prefix": "bus",
        "fav_add_prefix": "favadd_bus",
        "fav_show_prefix": "fav_bus",
        "fav_del_prefix": "favdel_bus",
        "toggle_day_prefix": "toggle_day_bus" # Префикс для переключения дня
    },
    TYPE_TROLLEYBUS: {
        "emoji": "🚎",
        "name_singular": "Троллейбус",
        "name_plural": "Троллейбусы",
        "callback_prefix": "trolleybus",
        "fav_add_prefix": "favadd_trolleybus",
        "fav_show_prefix": "fav_trolleybus",
        "fav_del_prefix": "favdel_trolleybus",
        "toggle_day_prefix": "toggle_day_trolleybus" # Префикс для переключения дня
    },
}

def get_current_day_type() -> str:
    """Возвращает текущий тип дня ('wd' или 'we')."""
    return DAY_WD if datetime.datetime.today().weekday() < 5 else DAY_WE

def get_opposite_day_type(day_type: str) -> str:
    """Возвращает противоположный тип дня."""
    return DAY_WE if day_type == DAY_WD else DAY_WD

def get_day_type_name(day_type: str, case: str = "nominative") -> str:
    """Возвращает название типа дня на русском."""
    # Можно добавить падежи при необходимости
    # Родительный (кого? чего?) - будних/выходных
    # Предложный (о ком? о чем?) - буднях/выходных
    # Винительный (кого? что?) - будни/выходные
    if day_type == DAY_WD:
        if case == "genitive": return "буднего дня"
        if case == "accusative": return "будни"
        if case == "prepositional": return "будних днях"
        return "будни" # именительный
    elif day_type == DAY_WE:
        if case == "genitive": return "выходного дня"
        if case == "accusative": return "выходные"
        if case == "prepositional": return "выходных днях"
        return "выходные" # именительный
    return "неизвестный день"

# --- Общие функции ---

async def show_directions(callback: CallbackQuery, transport_type: str, transport_data: dict, number: str):
    """Отображает выбор направления для указанного транспорта."""
    config = TRANSPORT_CONFIG[transport_type]
    try:
        vehicle = transport_data[number]
    except KeyError:
        await callback.answer(f"{config['name_singular']} №{number} не найден.", show_alert=True)
        return

    # Определяем маршруты на СЕГОДНЯ для отображения списка направлений
    today_type = get_current_day_type()
    routes_key = "route_weekdays" if today_type == DAY_WD else "route_weekends"
    routes = vehicle.get(routes_key, [])

    if not routes:
        # Проверим, есть ли маршруты на другой день
        opposite_day_type = get_opposite_day_type(today_type)
        opposite_routes_key = "route_weekdays" if opposite_day_type == DAY_WD else "route_weekends"
        has_opposite_routes = bool(vehicle.get(opposite_routes_key))

        message_text = (
            f"<b>{config['emoji']} {config['name_singular']} №{number}</b>\n\n"
            f"Нет данных о маршрутах на {get_day_type_name(today_type, 'accusative')}. "
        )
        if has_opposite_routes:
             message_text += f"Возможно, они есть на {get_day_type_name(opposite_day_type, 'accusative')}?"
        else:
             message_text += "Данных на другие дни также нет."

        # Кнопка назад все равно нужна
        kb = InlineKeyboardBuilder().button(text="🔙 Назад к списку", callback_data=f"back_to_{transport_type}_list")
        await callback.message.edit_text(message_text, reply_markup=kb.as_markup())
        return

    arrows = ["⬅️", "➡️"]
    direction_text = "\n".join([f"{arrows[i]} {route.get('name', 'Без названия')}" for i, route in enumerate(routes)])

    kb = InlineKeyboardBuilder()
    buttons = [
        InlineKeyboardButton(
            text=arrows[i],
            callback_data=f"route_{config['callback_prefix']}_{number}_{i}"
        ) for i in range(len(routes))
    ]
    kb.row(*buttons)
    kb.row(InlineKeyboardButton(text="🔙 Назад к списку", callback_data=f"back_to_{transport_type}_list"))

    try:
        await callback.message.edit_text(
            f"<b>{config['emoji']} {config['name_singular']} №{number}</b>\n\n"
            f"Доступные направления (на {get_day_type_name(today_type, 'accusative')}):\n{direction_text}\n\n"
            f"Выберите направление:",
            reply_markup=kb.as_markup()
        )
    except TelegramBadRequest:
        await callback.answer()


async def show_stops(callback: CallbackQuery, transport_type: str, transport_data: dict, number: str, route_idx: int):
    """Отображает список остановок для выбранного маршрута."""
    config = TRANSPORT_CONFIG[transport_type]
    # Определяем тип дня СЕЙЧАС, чтобы передать его в колбэки остановок
    initial_day_type = get_current_day_type()
    routes_key = "route_weekdays" if initial_day_type == DAY_WD else "route_weekends"

    try:
        vehicle = transport_data[number]
        routes = vehicle.get(routes_key, [])
        if not routes or route_idx >= len(routes):
            raise IndexError("Route index out of bounds or no routes found for today")
        route = routes[route_idx]
        stops = route.get("stops", [])
    except (KeyError, IndexError):
        await callback.answer(f"Ошибка: Не удалось найти маршрут для {config['name_singular']}а №{number} на {get_day_type_name(initial_day_type, 'accusative')}.", show_alert=True)
        return

    kb = InlineKeyboardBuilder()
    if stops:
        for i, stop in enumerate(stops):
            # Добавляем initial_day_type в callback_data
            stop_callback_data = f"stop_{config['callback_prefix']}_{number}_{route_idx}_{i}_{initial_day_type}"
            kb.button(text=stop.get('name', 'Без названия'), callback_data=stop_callback_data)
        kb.adjust(1)
        extra_text = f"Выберите остановку (расписание на {get_day_type_name(initial_day_type, 'accusative')}):"
    else:
        extra_text = "На данном маршруте нет остановок."

    kb.row(InlineKeyboardButton(text="🔙 Назад к направлениям", callback_data=f"{config['callback_prefix']}_{number}"))

    try:
        await callback.message.edit_text(
            f"<b>{config['emoji']} {config['name_singular']} №{number}</b>\n"
            f"<b>{route.get('name', 'Без названия')}</b>\n\n"
            f"{extra_text}",
            reply_markup=kb.as_markup()
        )
    except TelegramBadRequest:
        await callback.answer()


async def show_schedule_details(
    callback_or_message: CallbackQuery | Message,
    transport_type: str,
    transport_data: dict,
    number: str,
    route_idx: int,
    stop_idx: int,
    day_type: str, # Обязательный параметр
    is_from_favorites: bool = False
):
    """Отображает детальное расписание для остановки на указанный тип дня."""
    config = TRANSPORT_CONFIG[transport_type]
    message = callback_or_message.message if isinstance(callback_or_message, CallbackQuery) else callback_or_message
    user_id = callback_or_message.from_user.id

    logging.info(f"User {user_id}: Showing schedule details for {transport_type} #{number}, route:{route_idx}, stop:{stop_idx}, day:{day_type}, is_fav:{is_from_favorites}")

    times = []
    route_name = "Неизвестный маршрут"
    stop_name = "Неизвестная остановка"
    vehicle_number_display = number

    try:
        vehicle = transport_data[number]
        vehicle_number_display = vehicle.get('number', number)
        routes_key = "route_weekdays" if day_type == DAY_WD else "route_weekends"
        routes = vehicle.get(routes_key, [])

        if not routes or route_idx >= len(routes):
            raise IndexError(f"Route index {route_idx} out of bounds or no routes found for {day_type}")
        route = routes[route_idx]
        route_name = route.get('name', 'Без названия')
        stops = route.get("stops", [])

        if not stops or stop_idx >= len(stops):
             raise IndexError(f"Stop index {stop_idx} out of bounds or no stops found")
        stop = stops[stop_idx]
        stop_name = stop.get('name', 'Без названия')
        times = stop.get("times", [])

    except (KeyError, IndexError) as e:
        logging.warning(f"User {user_id}: Data error showing schedule: {e}")
        error_text = f"Ошибка: Не удалось найти данные для {config['name_singular']}а №{number} (маршрут {route_idx}, остановка {stop_idx}) на {get_day_type_name(day_type, 'accusative')}."
        if isinstance(callback_or_message, CallbackQuery):
            await callback_or_message.answer(error_text, show_alert=True)
        elif message:
             try: await message.edit_text(error_text)
             except TelegramBadRequest: pass
        return

    # --- Логика отображения и кнопки переключения ---
    kb = InlineKeyboardBuilder()
    text = ""
    schedule_exists = bool(times)
    opposite_day_type = get_opposite_day_type(day_type)
    opposite_schedule_exists = False

    # Проверяем наличие расписания на другой день
    try:
        opposite_routes_key = "route_weekdays" if opposite_day_type == DAY_WD else "route_weekends"
        opposite_routes = vehicle.get(opposite_routes_key, [])
        if opposite_routes and route_idx < len(opposite_routes):
            opposite_route = opposite_routes[route_idx]
            opposite_stops = opposite_route.get("stops", [])
            if opposite_stops and stop_idx < len(opposite_stops):
                opposite_stop = opposite_stops[stop_idx]
                if opposite_stop.get("times"):
                    opposite_schedule_exists = True
    except Exception as e:
        logging.error(f"User {user_id}: Error checking opposite schedule: {e}")

    schedule_day_name = get_day_type_name(day_type, 'accusative')
    opposite_day_name = get_day_type_name(opposite_day_type, 'accusative')

    base_text = (
        f"<b>{config['emoji']} {config['name_singular']} №{vehicle_number_display}</b>\n"
        f"<b>Маршрут:</b> {route_name}\n"
        f"<b>Остановка:</b> {stop_name}\n\n"
    )

    if schedule_exists:
        now = datetime.datetime.now()
        nearest = []
        now_time = now.time()
        current_day_matches_schedule_day = (get_current_day_type() == day_type)

        for t_str in times:
            try:
                t_dt = datetime.datetime.strptime(t_str, "%H:%M")
                # Ближайшие показываем только если тип дня совпадает с сегодняшним
                if current_day_matches_schedule_day and t_dt.time() >= now_time:
                    nearest.append(t_str)
            except ValueError: continue

        hours_schedule = {}
        for t in times:
            try:
                hour = int(t.split(":")[0])
                hours_schedule.setdefault(hour, []).append(t)
            except (ValueError, IndexError): continue

        # --- ВОЗВРАЩАЕМ ВАШ ФОРМАТ ВРЕМЕНИ ---
        formatted_schedule = "<code>" + "\n".join(
             ' '.join(sorted(minutes))
             for hour, minutes in sorted(hours_schedule.items())
        ) + "</code>"
        # --- КОНЕЦ ИЗМЕНЕНИЯ ---

        text = base_text + (
            f"<b>Расписание на {schedule_day_name}:</b>\n{formatted_schedule}\n\n"
        )
        # Показываем ближайшие только если отображается расписание на сегодня
        if current_day_matches_schedule_day:
            text += (
                f'<b>Ближайшие рейсы сегодня:</b>\n'
                f'{" ".join(list(map(lambda a: f"<code>{a}</code>", nearest[:5]))) if nearest else "Нет рейсов до конца дня"}'
            )
        else:
            text += f'<i>Ближайшие рейсы показаны только для сегодняшнего дня ({get_day_type_name(get_current_day_type(), "genitive")}).</i>'


        # Добавляем кнопку переключения, если есть расписание на другой день
        if opposite_schedule_exists:
            toggle_callback_data = f"{config['toggle_day_prefix']}_{number}_{route_idx}_{stop_idx}_{opposite_day_type}_{int(is_from_favorites)}"
            kb.button(text=f"🗓️ Показать на {opposite_day_name}", callback_data=toggle_callback_data)

    else: # Расписания на запрошенный тип дня нет
        text = base_text + f"❌ Расписание на {schedule_day_name} не найдено."
        if opposite_schedule_exists:
            text += f"\n\nПопробовать посмотреть на {opposite_day_name}?"
            toggle_callback_data = f"{config['toggle_day_prefix']}_{number}_{route_idx}_{stop_idx}_{opposite_day_type}_{int(is_from_favorites)}"
            kb.button(text=f"🗓️ Показать на {opposite_day_name}", callback_data=toggle_callback_data)
        else:
            text += "\n\nДанных на другие дни также нет."

    # --- Добавляем кнопки "В избранное"/"Удалить" и "Назад" ---
    fav_key = f"{number}_{route_idx}_{stop_idx}"
    if is_from_favorites:
        kb.button(text="🗑️ Удалить", callback_data=f"{config['fav_del_prefix']}_{fav_key}")
        back_callback = "back_to_fav_list"
    else:
        user_favs = utils.load_favorites(user_id)
        fav_section = "buses" if transport_type == TYPE_BUS else "trolleys"
        if fav_key not in user_favs.get(fav_section, {}):
             kb.button(text="⭐ В избранное", callback_data=f"{config['fav_add_prefix']}_{fav_key}")
        else:
             kb.button(text="✅ В избранном", callback_data="dummy_in_favorites") # Dummy callback

        back_callback = f"route_{config['callback_prefix']}_{number}_{route_idx}"

    kb.button(text="🔙 Назад", callback_data=back_callback)
    kb.adjust(1) # Кнопки друг под другом

    # Отправка или редактирование сообщения
    if not message: return
    try:
        # Избегаем ошибки "message is not modified"
        if message.html_text != text or message.reply_markup != kb.as_markup():
            await message.edit_text(text, reply_markup=kb.as_markup())
            if isinstance(callback_or_message, CallbackQuery): await callback_or_message.answer()
        elif isinstance(callback_or_message, CallbackQuery):
            await callback_or_message.answer() # Просто закрываем часики
    except TelegramBadRequest as e:
         logging.warning(f"User {user_id}: Error editing schedule message: {e}")
         if isinstance(callback_or_message, CallbackQuery):
             await callback_or_message.answer("Не удалось обновить расписание.")

# --- Функции для обработки колбэков "Назад" ---

async def back_to_transport_list(callback: CallbackQuery, transport_type: str, start_handler_func):
    """Возвращает к списку автобусов/троллейбусов."""
    if callback.message:
        await start_handler_func(callback.message)
        try:
           await callback.message.edit_reply_markup(reply_markup=None)
        except TelegramBadRequest: pass
    await callback.answer()

async def back_to_directions(callback: CallbackQuery, transport_type: str, transport_data: dict, number: str):
    """Возвращает к выбору направления."""
    await show_directions(callback, transport_type, transport_data, number)
    await callback.answer()

async def back_to_stops(callback: CallbackQuery, transport_type: str, transport_data: dict, number: str, route_idx: int):
    """Возвращает к выбору остановки."""
    await show_stops(callback, transport_type, transport_data, number, route_idx)
    await callback.answer()

# --- Обработчик для dummy кнопки ---
async def handle_dummy_callback(callback: CallbackQuery):
    """Просто отвечает на колбэк."""
    await callback.answer("Это уже в избранном.")

# --- END OF FILE common_handlers.py ---