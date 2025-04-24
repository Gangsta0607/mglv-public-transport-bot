from bs4 import BeautifulSoup
import requests
import re
import json
import os
import time
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from typing import List, Dict
import logging
import sys
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# === Настройка логгера ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

from dotenv import load_dotenv

load_dotenv()

TROLLEYBUS_SCHEDULE = os.getenv("TROLLEYBUS_SCHEDULE_PATH")

def saveScheduleToFile(Trolleybuses: List[Dict]):
    try:
        with open(TROLLEYBUS_SCHEDULE, "w", encoding="utf-8") as f:
            json.dump(Trolleybuses, f, indent=4, ensure_ascii=False)
        logging.info(f"Сохранено расписание ({len(Trolleybuses)} троллейбусов)")
    except Exception as e:
        logging.error(f"Ошибка при сохранении: {e}")

def loadScheduleFromFile() -> List[Dict]:
    if not os.path.exists(TROLLEYBUS_SCHEDULE):
        return None
    try:
        with open(TROLLEYBUS_SCHEDULE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.warning(f"Ошибка загрузки файла: {e}")
        return None

def getRoutes(trolleybus_number, table, route_name):
    try:
        name = list(map(lambda q: q.strip().title(), route_name.split("–")))
        _ = list(table.children)
        _ = list(filter(lambda a: a != "\n", _))
        names = _[::2]
        times = _[1::2]
        break_index = 0
        for i in range(len(names) - 1):
            if names[i] == names[i + 1]:
                break_index = i
                break
        
        route1 = {"trolleybus_number": trolleybus_number, "name": " - ".join(name), "stops": []}
        route2 = {"trolleybus_number": trolleybus_number, "name": " - ".join(name[::-1]), "stops": []}

        for i, data in enumerate(zip(names, times)):
            stop_name, time = list(map(lambda a: a.text, data))
            stop_name = stop_name.title().replace("Мвд", "МВД").replace("Оао", "ОАО").replace("тэц", "ТЭЦ")
            (route1 if i <= break_index else route2)["stops"].append({"name": stop_name, "times": time.split(", ")})
        
        return [route1, route2]
    except Exception as e:
        logging.warning(f"Ошибка в таблице маршрута {trolleybus_number}: {e}")
    return []

def getSchedule(url, route_name):
    try:
        response = requests.get(url, timeout=10, verify=False)
        soup = BeautifulSoup(response.text, "html.parser")

        title = soup.find("strong", string=re.compile("Маршрут движения троллейбуса"))
        if not title:
            raise ValueError("Не найден заголовок маршрута")

        trolleybus_number = title.text.split("№")[1][:-1].strip()

        def find_tables(keyword):
            h2 = soup.find("h2", string=re.compile(keyword))
            if not h2:
                return []
            t1 = h2.find_next_sibling()
            if t1:
                return getRoutes(trolleybus_number, t1, route_name)
            return []

        return [find_tables("будние дни"), find_tables("выходные дни")]

    except Exception as e:
        logging.error(f"Ошибка при получении расписания с {url}: {e}")
        return [[], []]

def process_trolleybus(trolleybus_html, base_url):
    try:
        tds = trolleybus_html.find_all("td")
        if len(tds) < 3:
            return None
        trolleybus_num, route_name, link_td = map(lambda a: a.text, tds)
        link = tds[-1].a["href"]

        url = base_url + link
        route_weekdays, route_weekends = getSchedule(url, route_name)

        return {
            "number": trolleybus_num,
            "route_name": route_name.title(),
            "route_weekdays": route_weekdays,
            "route_weekends": route_weekends
        }
    except Exception as e:
        logging.warning(f"Ошибка обработки троллейбуса: {e}")
        return None

def getTrolleybusesParallel():
    start_time = time.time()
    if len(sys.argv) == 1:
        trolleybuses = loadScheduleFromFile()
    else: 
        trolleybuses = None
    if trolleybuses:
        logging.info("Загружено из кэша.")
    else:
        url = "https://mogilev.biz/spravka/transport/troll/"
        base_url = "https://mogilev.biz"
        response = requests.get(url, verify=False)
        soup = BeautifulSoup(response.text, "html.parser")

        trolleybus_rows = soup.find("table", class_="table").find_all("tr")[1:]
        total = len(trolleybus_rows)
        
        print("Скачиваем расписания:")
        with ProcessPoolExecutor(max_workers=multiprocessing.cpu_count()) as executor:
            results = []
            for i, result in enumerate(executor.map(process_trolleybus, trolleybus_rows, [base_url] * total)):
                if result:
                    results.append(result)
                print(f"[{i+1}/{total}] ✓", end="\r", flush=True)

        trolleybuses = results
        saveScheduleToFile(trolleybuses)

    elapsed = time.time() - start_time
    logging.info(f"Обработка завершена за {elapsed:.2f} сек.")
    return {trolleybus["number"]: trolleybus for trolleybus in trolleybuses}

if __name__ == "__main__":
    getTrolleybusesParallel()