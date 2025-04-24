# --- START OF FILE utils.py ---

import parsers.trolleybus_parser
import parsers.bus_parser

import json
import os
import datetime
from dotenv import load_dotenv

load_dotenv()

FAVORITES_PATH = os.getenv("FAVORITES_PATH", "favorites.json") # Значение по умолчанию
TROLLEYBUS_SCHEDULE_PATH = os.getenv("TROLLEYBUS_SCHEDULE_PATH") # Пути к исходным данным (если парсеры их читают)
BUS_SCHEDULE_PATH = os.getenv("BUS_SCHEDULE_PATH")

# --- Кэширование данных расписания ---
_bus_schedule_cache = None
_trolleybus_schedule_cache = None
_cache_expiry_time = datetime.timedelta(days=7) # Время жизни кэша - 7 дней
_bus_cache_timestamp = None
_trolleybus_cache_timestamp = None

def _is_cache_valid(timestamp):
    """Проверяет, действителен ли кэш."""
    if timestamp is None:
        return False
    return (datetime.datetime.now() - timestamp) < _cache_expiry_time

def getBusSchedule(force_reload: bool = False):
    """Возвращает данные расписания автобусов, используя кэш."""
    global _bus_schedule_cache, _bus_cache_timestamp
    now = datetime.datetime.now()
    if force_reload or not _is_cache_valid(_bus_cache_timestamp) or _bus_schedule_cache is None:
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Reloading bus schedule data...")
        try:
            # Предполагаем, что парсеры возвращают данные или бросают исключение
            _bus_schedule_cache = parsers.bus_parser.getBusesParallel()
            _bus_cache_timestamp = now
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Bus schedule data reloaded successfully.")
        except Exception as e:
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Error reloading bus schedule: {e}")
            # Возвращаем старый кэш, если он есть, иначе пустой словарь
            return _bus_schedule_cache if _bus_schedule_cache else {}
    return _bus_schedule_cache

def getTrolleybusSchedule(force_reload: bool = False):
    """Возвращает данные расписания троллейбусов, используя кэш."""
    global _trolleybus_schedule_cache, _trolleybus_cache_timestamp
    now = datetime.datetime.now()
    if force_reload or not _is_cache_valid(_trolleybus_cache_timestamp) or _trolleybus_schedule_cache is None:
        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Reloading trolleybus schedule data...")
        try:
            # Предполагаем, что парсеры возвращают данные или бросают исключение
            _trolleybus_schedule_cache = parsers.trolleybus_parser.getTrolleybusesParallel()
            _trolleybus_cache_timestamp = now
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Trolleybus schedule data reloaded successfully.")
        except Exception as e:
            print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Error reloading trolleybus schedule: {e}")
             # Возвращаем старый кэш, если он есть, иначе пустой словарь
            return _trolleybus_schedule_cache if _trolleybus_schedule_cache else {}
    return _trolleybus_schedule_cache

def force_reload_all_schedules():
    """Принудительно перезагружает кэш обоих типов транспорта."""
    print("Forcing reload of all schedules...")
    getBusSchedule(force_reload=True)
    getTrolleybusSchedule(force_reload=True)
    print("All schedules reloaded.")


# --- Работа с избранным (JSON) ---

def load_favorites(user_id: int) -> dict:
    """
    Загружает избранное для пользователя.
    Возвращает словарь вида {'buses': {}, 'trolleys': {}}
    """
    user_id_str = str(user_id)
    default_favs = {"buses": {}, "trolleys": {}}
    if not os.path.exists(FAVORITES_PATH):
        return default_favs
    try:
        with open(FAVORITES_PATH, "r", encoding="utf-8") as f:
            all_data = json.load(f)
        # Возвращаем данные пользователя или структуру по умолчанию
        return all_data.get(user_id_str, default_favs)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading favorites file: {e}")
        return default_favs # Возвращаем пустую структуру при ошибке

def save_favorites(user_id: int, favs: dict):
    """
    Сохраняет избранное для пользователя.
    ОПАСНОСТЬ: Не потокобезопасно для JSON! Используйте с осторожностью.
    """
    user_id_str = str(user_id)
    all_data = {}
    if os.path.exists(FAVORITES_PATH):
        try:
            with open(FAVORITES_PATH, "r", encoding="utf-8") as f:
                all_data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error reading favorites file before saving: {e}")
            # В случае ошибки чтения, пытаемся сохранить только данные текущего пользователя,
            # но это может привести к потере данных других пользователей!
            all_data = {} # Перезаписываем все

    all_data[user_id_str] = favs
    try:
        with open(FAVORITES_PATH, "w", encoding="utf-8") as f:
            json.dump(all_data, f, ensure_ascii=False, indent=4)
    except IOError as e:
        print(f"Error writing favorites file: {e}")

# --- END OF FILE utils.py ---