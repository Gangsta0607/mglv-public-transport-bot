# --- START OF FILE favorites.py ---

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
import utils
from handlers import common_handlers
import datetime
import logging # Добавим логирование

# Логируем момент загрузки модуля и создания роутера
logging.info("handlers/favorites.py loaded and router being created.")
router = Router()

# Получаем конфиги для удобства
BUS_CONFIG = common_handlers.TRANSPORT_CONFIG[common_handlers.TYPE_BUS]
TROLLEYBUS_CONFIG = common_handlers.TRANSPORT_CONFIG[common_handlers.TYPE_TROLLEYBUS]

# --- Вспомогательная функция для генерации сообщения со списком избранного ---
def _build_favorites_message(user_id: int) -> tuple[str, InlineKeyboardBuilder | None]:
    """Строит текст и клавиатуру для списка избранного."""
    favs = utils.load_favorites(user_id)
    bus_favs = favs.get("buses", {})
    trolley_favs = favs.get("trolleys", {})

    # Если избранное пусто, создаем кнопки для перехода к спискам
    if not bus_favs and not trolley_favs:
        kb = InlineKeyboardBuilder()
        kb.button(
            text=f"{BUS_CONFIG['emoji']} Показать автобусы",
            callback_data=f"back_to_{common_handlers.TYPE_BUS}_list" # Существующий callback
        )
        kb.button(
            text=f"{TROLLEYBUS_CONFIG['emoji']} Показать троллейбусы",
            callback_data=f"back_to_{common_handlers.TYPE_TROLLEYBUS}_list" # Существующий callback
        )
        kb.adjust(1) # Кнопки друг под другом
        return "У вас пока нет избранных остановок.\n\nВыберите, что посмотреть:", kb # Возвращаем текст и билдер

    # Если избранное не пусто, формируем список
    kb = InlineKeyboardBuilder()
    msg_text = '<b>⭐ Ваше избранное:</b>\n\n'
    fav_counter = 0

    # Автобусы
    if bus_favs:
        msg_text += f"<b>{BUS_CONFIG['emoji']} {BUS_CONFIG['name_plural']}:</b>\n"
        sorted_bus_keys = sorted(bus_favs.keys())
        for key in sorted_bus_keys:
            val = bus_favs[key]
            fav_counter += 1
            kb.button(text=f"#{fav_counter}", callback_data=f"{BUS_CONFIG['fav_show_prefix']}_{key}")
            msg_text += (f"{fav_counter}. <b>№{val.get('number', '?')}</b>, "
                         f"ост. \"{val.get('stop', 'Неизвестно')}\" "
                         f"(<i>{val.get('route', 'Маршрут не указан')}</i>)\n")
        msg_text += "\n" # Отступ между типами транспорта

    # Троллейбусы
    if trolley_favs:
        msg_text += f"<b>{TROLLEYBUS_CONFIG['emoji']} {TROLLEYBUS_CONFIG['name_plural']}:</b>\n"
        sorted_trolley_keys = sorted(trolley_favs.keys())
        for key in sorted_trolley_keys:
            val = trolley_favs[key]
            fav_counter += 1
            kb.button(text=f"#{fav_counter}", callback_data=f"{TROLLEYBUS_CONFIG['fav_show_prefix']}_{key}")
            msg_text += (f"{fav_counter}. <b>№{val.get('number', '?')}</b>, "
                         f"ост. \"{val.get('stop', 'Неизвестно')}\" "
                         f"(<i>{val.get('route', 'Маршрут не указан')}</i>)\n")

    kb.adjust(5) # По 5 кнопок в ряду
    return msg_text, kb # Возвращаем текст и билдер


# --- Основные хендлеры ---

# Обработчик для кнопки "⭐ Избранное"
@router.message(F.text == "⭐ Избранное")
async def show_favorites_handler(message: Message):
    """Отображает список избранного в ответ на команду."""
    logging.info(f"HANDLER: show_favorites_handler triggered for user {message.from_user.id} ({message.from_user.username})")
    user_id = message.from_user.id
    msg_text, kb = _build_favorites_message(user_id)

    reply_markup = kb.as_markup() if kb else None

    # Разбиваем сообщение, если длинное
    if len(msg_text) > 4096:
         # Отправляем кнопки только с последней частью
         await message.answer(msg_text[:4090] + "...") # Обрезаем
         await message.answer("... продолжение списка:", reply_markup=reply_markup)
    else:
        await message.answer(msg_text, reply_markup=reply_markup)


# --- Добавление в избранное ---
async def _add_favorite_common(callback: CallbackQuery, transport_type: str, transport_data: dict, key: str):
    """Общая логика добавления в избранное."""
    config = common_handlers.TRANSPORT_CONFIG[transport_type]
    fav_section = "buses" if transport_type == common_handlers.TYPE_BUS else "trolleys"
    user_id = callback.from_user.id
    logging.info(f"User {user_id}: Attempting to add favorite {transport_type} with key {key}")

    try:
        number, route_idx_str, stop_idx_str = key.split("_")
        route_idx = int(route_idx_str)
        stop_idx = int(stop_idx_str)

        # Валидация данных перед сохранением
        vehicle = transport_data[number]
        today = datetime.datetime.today().weekday() # Нужен для определения ключа маршрутов
        routes_key = "route_weekdays" if today < 5 else "route_weekends"
        # Используем get для безопасного доступа и проверки наличия маршрутов/остановок
        routes = vehicle.get(routes_key, [])
        if route_idx >= len(routes): raise IndexError("Route index out of range")
        route = routes[route_idx]
        stops = route.get("stops", [])
        if stop_idx >= len(stops): raise IndexError("Stop index out of range")
        stop = stops[stop_idx]

        # Загружаем и обновляем избранное
        favs = utils.load_favorites(user_id)
        # Убеждаемся, что секция существует
        if fav_section not in favs:
            favs[fav_section] = {}

        favs[fav_section][key] = {
            "number": vehicle.get('number', number), # Сохраняем номер из данных, если есть
            "route": route.get('name', 'Без названия'),
            "stop": stop.get('name', 'Без названия')
        }
        utils.save_favorites(user_id, favs)
        logging.info(f"User {user_id}: Successfully added favorite {key}")
        await callback.answer(f"{config['name_singular']} добавлен в избранное ⭐")

    except (KeyError, IndexError, ValueError) as e:
        logging.warning(f"User {user_id}: Error adding favorite {key} - Data validation failed: {type(e).__name__} {e.args}")
        await callback.answer(f"Ошибка: Не удалось найти данные для добавления {config['name_singular']}а в избранное.", show_alert=True)
    except Exception as e:
         # Логируем неожиданные ошибки
         logging.error(f"User {user_id}: Unexpected error adding favorite {key}: {e}", exc_info=True)
         await callback.answer(f"Произошла ошибка при добавлении в избранное.", show_alert=True)


@router.callback_query(F.data.startswith(f"{BUS_CONFIG['fav_add_prefix']}_"))
async def add_bus_favorite_handler(callback: CallbackQuery):
    """Добавляет автобус в избранное."""
    try:
        # favadd_bus_KEY -> извлекаем ключ
        key = callback.data.split("_", 2)[2]
        bus_data = utils.getBusSchedule()
        await _add_favorite_common(callback, common_handlers.TYPE_BUS, bus_data, key)
    except IndexError:
         logging.warning(f"User {callback.from_user.id}: Invalid add bus favorite callback format: {callback.data}")
         await callback.answer("Ошибка: Некорректный формат данных для добавления.", show_alert=True)


@router.callback_query(F.data.startswith(f"{TROLLEYBUS_CONFIG['fav_add_prefix']}_"))
async def add_trolleybus_favorite_handler(callback: CallbackQuery):
    """Добавляет троллейбус в избранное."""
    try:
        # favadd_trolleybus_KEY -> извлекаем ключ
        key = callback.data.split("_", 2)[2]
        trolleybus_data = utils.getTrolleybusSchedule()
        await _add_favorite_common(callback, common_handlers.TYPE_TROLLEYBUS, trolleybus_data, key)
    except IndexError:
         logging.warning(f"User {callback.from_user.id}: Invalid add trolleybus favorite callback format: {callback.data}")
         await callback.answer("Ошибка: Некорректный формат данных для добавления.", show_alert=True)


# --- Просмотр расписания из избранного ---

@router.callback_query(F.data.startswith(f"{BUS_CONFIG['fav_show_prefix']}_"))
async def show_fav_bus_schedule_handler(callback: CallbackQuery):
    """Показывает расписание для избранного автобуса."""
    logging.info(f"User {callback.from_user.id}: Showing favorite bus schedule via callback {callback.data}")
    try:
        # fav_bus_KEY -> извлекаем ключ
        key = callback.data.split("_", 2)[2]
        number, route_idx_str, stop_idx_str = key.split("_")
        route_idx = int(route_idx_str)
        stop_idx = int(stop_idx_str)
        bus_data = utils.getBusSchedule()
        # Определяем ТЕКУЩИЙ тип дня для ПЕРВОНАЧАЛЬНОГО показа
        initial_day_type = common_handlers.get_current_day_type()
        await common_handlers.show_schedule_details(
            callback,
            common_handlers.TYPE_BUS,
            bus_data,
            number,
            route_idx,
            stop_idx,
            day_type=initial_day_type, # Передаем начальный тип дня
            is_from_favorites=True     # Указываем, что это из избранного
        )
    except (IndexError, ValueError) as e:
        logging.warning(f"User {callback.from_user.id}: Invalid favorite bus callback data: {callback.data} - {e}")
        await callback.answer("Ошибка: Некорректный формат данных избранного.", show_alert=True)
    except KeyError as e:
         logging.warning(f"User {callback.from_user.id}: Favorite bus key {key} data not found: {e}")
         await callback.answer("Ошибка: Автобус из избранного не найден в текущем расписании.", show_alert=True)


@router.callback_query(F.data.startswith(f"{TROLLEYBUS_CONFIG['fav_show_prefix']}_"))
async def show_fav_trolleybus_schedule_handler(callback: CallbackQuery):
    """Показывает расписание для избранного троллейбуса."""
    logging.info(f"User {callback.from_user.id}: Showing favorite trolleybus schedule via callback {callback.data}")
    try:
        # fav_trolleybus_KEY -> извлекаем ключ
        key = callback.data.split("_", 2)[2]
        number, route_idx_str, stop_idx_str = key.split("_")
        route_idx = int(route_idx_str)
        stop_idx = int(stop_idx_str)
        trolleybus_data = utils.getTrolleybusSchedule()
        # Определяем ТЕКУЩИЙ тип дня для ПЕРВОНАЧАЛЬНОГО показа
        initial_day_type = common_handlers.get_current_day_type()
        await common_handlers.show_schedule_details(
            callback,
            common_handlers.TYPE_TROLLEYBUS,
            trolleybus_data,
            number,
            route_idx,
            stop_idx,
            day_type=initial_day_type, # Передаем начальный тип дня
            is_from_favorites=True     # Указываем, что это из избранного
        )
    except (IndexError, ValueError) as e:
        logging.warning(f"User {callback.from_user.id}: Invalid favorite trolleybus callback data: {callback.data} - {e}")
        await callback.answer("Ошибка: Некорректный формат данных избранного.", show_alert=True)
    except KeyError as e:
        logging.warning(f"User {callback.from_user.id}: Favorite trolleybus key {key} data not found: {e}")
        await callback.answer("Ошибка: Троллейбус из избранного не найден в текущем расписании.", show_alert=True)


# --- Удаление из избранного ---

async def _delete_favorite_common(callback: CallbackQuery, transport_type: str, key: str):
    """Общая логика удаления из избранного и обновления сообщения."""
    fav_section = "buses" if transport_type == common_handlers.TYPE_BUS else "trolleys"
    user_id = callback.from_user.id
    logging.info(f"User {user_id}: Attempting to delete favorite {transport_type} with key {key}")

    favs = utils.load_favorites(user_id)

    # Проверяем наличие ключа в нужной секции
    if fav_section in favs and key in favs[fav_section]:
        del favs[fav_section][key] # Удаляем элемент
        utils.save_favorites(user_id, favs) # Сохраняем изменения
        logging.info(f"User {user_id}: Successfully deleted favorite {key}")
        await callback.answer("Удалено из избранного")

        # Обновляем сообщение, показывая актуальный список избранного (или кнопки, если список стал пустым)
        msg_text, kb = _build_favorites_message(user_id)
        reply_markup = kb.as_markup() if kb else None
        try:
            # Проверяем, что сообщение существует перед редактированием
            if callback.message:
                # Избегаем ошибки "message is not modified"
                if callback.message.html_text != msg_text or callback.message.reply_markup != reply_markup:
                    await callback.message.edit_text(msg_text, reply_markup=reply_markup)
                # Если ничего не изменилось, просто закрываем колбэк (уже сделано в answer выше)
        except TelegramBadRequest as e:
            # Логируем ошибку редактирования
            logging.error(f"User {user_id}: Error editing message after favorite delete: {e}")
            # Если не удалось отредактировать, отправим новым сообщением
            if callback.message: # Отправляем ответ к исходному сообщению
                await callback.message.answer("Запись удалена. Ваш обновленный список избранного:")
                await callback.message.answer(msg_text, reply_markup=reply_markup)
    else:
        # Элемент уже удален или не существовал
        logging.warning(f"User {user_id}: Attempted to delete non-existent favorite key {key} in section {fav_section}")
        await callback.answer("Эта запись уже удалена из избранного.", show_alert=True)
        # Можно также обновить сообщение на всякий случай, если оно неактуально
        msg_text, kb = _build_favorites_message(user_id)
        reply_markup = kb.as_markup() if kb else None
        try:
            if callback.message and (callback.message.html_text != msg_text or callback.message.reply_markup != reply_markup):
                 await callback.message.edit_text(msg_text, reply_markup=reply_markup)
        except TelegramBadRequest: pass # Игнорируем ошибку, если не удалось обновить


@router.callback_query(F.data.startswith(f"{BUS_CONFIG['fav_del_prefix']}_"))
async def delete_bus_favorite_handler(callback: CallbackQuery):
    """Удаляет автобус из избранного."""
    try:
        # favdel_bus_KEY -> извлекаем ключ
        key = callback.data.split("_", 2)[2]
        await _delete_favorite_common(callback, common_handlers.TYPE_BUS, key)
    except IndexError:
        logging.warning(f"User {callback.from_user.id}: Invalid delete bus favorite callback format: {callback.data}")
        await callback.answer("Ошибка: Некорректный формат данных для удаления.", show_alert=True)

@router.callback_query(F.data.startswith(f"{TROLLEYBUS_CONFIG['fav_del_prefix']}_"))
async def delete_trolleybus_favorite_handler(callback: CallbackQuery):
    """Удаляет троллейбус из избранного."""
    try:
        # favdel_trolleybus_KEY -> извлекаем ключ
        key = callback.data.split("_", 2)[2]
        await _delete_favorite_common(callback, common_handlers.TYPE_TROLLEYBUS, key)
    except IndexError:
        logging.warning(f"User {callback.from_user.id}: Invalid delete trolleybus favorite callback format: {callback.data}")
        await callback.answer("Ошибка: Некорректный формат данных для удаления.", show_alert=True)


# --- Возврат к списку избранного ---

@router.callback_query(F.data == "back_to_fav_list")
async def back_to_favorites_handler(callback: CallbackQuery):
    """Обновляет текущее сообщение, показывая список избранного."""
    user_id = callback.from_user.id
    logging.info(f"User {user_id}: Returning to favorites list.")
    # Эта функция теперь вернет либо список с кнопками, либо сообщение с кнопками "Показать..."
    msg_text, kb = _build_favorites_message(user_id)
    reply_markup = kb.as_markup() if kb else None
    try:
        # Проверяем, что сообщение существует
        if callback.message:
             # Избегаем ошибки "message is not modified"
            if callback.message.html_text != msg_text or callback.message.reply_markup != reply_markup:
                await callback.message.edit_text(msg_text, reply_markup=reply_markup)
                await callback.answer() # Закрываем часики после успешного редактирования
            else:
                await callback.answer() # Просто закрыть часики, если ничего не изменилось
        else:
             await callback.answer() # Закрыть часики, если сообщения нет

    except TelegramBadRequest as e:
        logging.error(f"User {user_id}: Error editing message on back_to_fav_list: {e}")
        await callback.answer("Не удалось обновить список.")

# --- END OF FILE favorites.py ---