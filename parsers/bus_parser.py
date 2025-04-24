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
BUS_SCHEDULE = os.getenv("BUS_SCHEDULE_PATH")

def saveScheduleToFile(buses: List[Dict]):
    try:
        with open(BUS_SCHEDULE, "w", encoding="utf-8") as f:
            json.dump(buses, f, indent=4, ensure_ascii=False)
        logging.info(f"Сохранено расписание ({len(buses)} автобусов)")
    except Exception as e:
        logging.error(f"Ошибка при сохранении: {e}")

def loadScheduleFromFile() -> List[Dict]:
    if not os.path.exists(BUS_SCHEDULE):
        return None
    try:
        with open(BUS_SCHEDULE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.warning(f"Ошибка загрузки файла: {e}")
        return None

def getRoutes(bus_number, table1, table2):
    routes = []
    for table in [table1, table2]:
        try:
            name = table.thead.tr.th.center.strong.text.strip()
            route = {"bus_number": bus_number, "name": name, "stops": []}
            for row in table.tbody.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue
                stop_name = cells[0].text.strip()
                schedule_cell = cells[1]
                times = []
                for div in schedule_cell.find_all("div"):
                    try:
                        hour = div.b.text.strip()
                        raw = div.decode_contents().split("</b>")[1]
                        minutes = re.findall(r"\d{2}", raw)
                        times.extend([f"{hour}:{minute}" for minute in minutes])
                    except Exception:
                        continue
                route["stops"].append({"name": stop_name, "times": times})
            routes.append(route)
        except Exception as e:
            logging.warning(f"Ошибка в таблице маршрута {bus_number}: {e}")
    return routes

def getSchedule(url):
    try:
        response = requests.get(url, timeout=10, verify=False)
        soup = BeautifulSoup(response.text, "html.parser")

        title = soup.find("strong", string=re.compile("Маршрут движения автобуса"))
        if not title:
            raise ValueError("Не найден заголовок маршрута")

        bus_number = title.text.split("№")[1][:-1].strip()

        def find_tables(keyword):
            h2 = soup.find("h2", string=re.compile(keyword))
            if not h2:
                return []
            t1 = h2.find_next_sibling()
            t2 = t1.find_next_sibling() if t1 and t1.name != "p" else None
            if t1 and t2:
                return getRoutes(bus_number, t1, t2)
            return []

        return [find_tables("будние дни"), find_tables("выходные дни")]

    except Exception as e:
        logging.error(f"Ошибка при получении расписания с {url}: {e}")
        return [[], []]

def process_bus(bus_html, base_url):
    try:
        tds = bus_html.find_all("td")
        if len(tds) < 2:
            return None
        desc_td, link_td = tds
        span = desc_td.find("span")
        bus_num = span.text.split("№")[1].strip() if span else "??"
        route_name = span.next_sibling.strip() if span and span.next_sibling else "Без названия"

        if bus_num in ["50", "28к"]:
            return None

        relative_url = link_td.find("a")["href"]
        url = base_url + relative_url
        route_weekdays, route_weekends = getSchedule(url)

        return {
            "number": bus_num,
            "route_name": route_name,
            "route_weekdays": route_weekdays,
            "route_weekends": route_weekends
        }
    except Exception as e:
        logging.warning(f"Ошибка обработки автобуса: {e}")
        return None

def getBusesParallel():
    start_time = time.time()
    buses = loadScheduleFromFile()
    if buses:
        logging.info("Загружено из кэша.")
    else:
        url = "https://mogilev.biz/spravka/transport/busgor/"
        base_url = "https://mogilev.biz"
        response = requests.get(url, verify=False)
        soup = BeautifulSoup(response.text, "html.parser")

        bus_rows = soup.find("table", class_="adapt-list-schedule").find_all("tr")[1:]
        total = len(bus_rows)

        print("Скачиваем расписания:")
        with ProcessPoolExecutor(max_workers=multiprocessing.cpu_count()) as executor:
            results = []
            for i, result in enumerate(executor.map(process_bus, bus_rows, [base_url] * total)):
                if result:
                    results.append(result)
                print(f"[{i+1}/{total}] ✓", end="\r", flush=True)

        buses = results
        saveScheduleToFile(buses)

    elapsed = time.time() - start_time
    logging.info(f"Обработка завершена за {elapsed:.2f} сек.")
    return {bus["number"]: bus for bus in buses}

if __name__ == "__main__":
    getBusesParallel()