"""
Smoke-тест собранного бандла.

Запускается как ЗАМОРОЖЕННЫЙ exe (PyInstaller), не как обычный скрипт.
Проверяет, что все модули, которые тянет реальное приложение, попали
в бандл и импортируются.

Зачем это нужно: PyInstaller НЕ падает на сломанном модуле. Он компилирует
синтаксис лениво, битый модуль просто молча выпадает из бандла, сборка
заканчивается словами "Build complete!", а пользователь получает exe,
который падает с ModuleNotFoundError при запуске. Этот тест — единственное,
что такое ловит.

Собирается теми же флагами, что и релиз, и отличается только --console
вместо --windowed, чтобы проверялся ровно тот набор зависимостей и данных,
который уезжает пользователю.

ВНИМАНИЕ: импорты ниже должны быть ЛИТЕРАЛЬНЫМИ (`import X`), а не через
importlib.import_module. PyInstaller анализирует импорты статически и
динамические в бандл не кладёт. Проверено экспериментально: с
importlib бандл собирается "успешно", а на запуске падает на 16 модулей.

При добавлении нового модуля в приложение его нужно добавить и сюда.
"""

import os
import sys

# Страховка от кодировок консоли раннера
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

failures = []

# Модули приложения. Порядок = порядок графа импортов run_gui.py/main.py.
try:
    import app_config
    import logger
    import error_handler
    from services import cbr_rate
    from services import moex_data
    from analysis import classification
    from analysis import filters
    from analysis import taxes
    from analysis import yield_calculator
    from ui import console
    from ui import gui_app
    import run_gui
    import main

    # Сторонние пакеты, обязательные в бандле.
    import pandas
    import requests
    import customtkinter
    import tkinter
    import tkcalendar
except BaseException as _e:
    # Импорты жёсткие и идут по одному, поэтому первое же падение
    # обрывает всю цепочку: перечислять «отсутствующие» нельзя —
    # до них мы просто не дошли. Показываем, на чём именно встали,
    # и имя модуля из сообщения, чтобы в логе CI была причина.
    _missing = str(_e).split("'")[1] if "'" in str(_e) else "неизвестно"
    print(f"SMOKE TEST FAILED: жёсткий импорт упал на модуле "
          f"'{_missing}' — {type(_e).__name__}: {_e}")
    print(f"\nМодуль '{_missing}' не попал в бандл. Проверь, что:")
    print("  1. файл на месте и не пустой;")
    print("  2. в нём нет синтаксической ошибки (PyInstaller такие файлы")
    print("     МОЛЧА исключает из бандла и всё равно пишет 'Build complete!');")
    print("  3. сборка выполнена с нуля — rm -rf build dist *.spec.")
    sys.exit(1)

# (метка, объект) — импорты уже выполнены выше, осталось их проверить.
CHECKED = [
    ("app_config", app_config),
    ("logger", logger),
    ("error_handler", error_handler),
    ("services.cbr_rate", cbr_rate),
    ("services.moex_data", moex_data),
    ("analysis.classification", classification),
    ("analysis.filters", filters),
    ("analysis.taxes", taxes),
    ("analysis.yield_calculator", yield_calculator),
    ("ui.console", console),
    ("ui.gui_app", gui_app),
    ("run_gui", run_gui),
    ("main", main),
    ("pandas", pandas),
    ("requests", requests),
    ("customtkinter", customtkinter),
    ("tkinter", tkinter),
    ("tkcalendar", tkcalendar),
]

# Ресурсы, которые кладутся через --add-data. Проверяем, что сборщик их
# действительно положил и что они не пустые.
DATA_FILES = ["app_icon.ico", "app_icon.png"]

print(f"Smoke test: проверка {len(CHECKED)} импортов, "
      f"{len(DATA_FILES)} ресурсов\n")

for label, obj in CHECKED:
    if obj is None:
        print(f"FAIL  import  {label}: модуль импортирован как None")
        failures.append(f"{label}: импортирован как None")
        continue
    print(f"OK    import  {label}")

# Проверяем, что конфиг не просто импортируется, а содержит данные.
n_scen = len(getattr(app_config, "RATE_SCENARIOS", {}) or {})
print(f"\n      сценариев ставок: {n_scen}, "
      f"налог: {getattr(app_config, 'TAX_RATE', 'нет')}, "
      f"параметров API: {len(getattr(app_config, 'API_PARAMS', {}) or {})}")
if n_scen == 0:
    print("FAIL  config  RATE_SCENARIOS пуст — конфиг загрузился, "
          "но данных нет")
    failures.append("RATE_SCENARIOS пуст")

# Проверяем, что у GUI-класса есть точка входа, которую зовёт run_gui.py:
# если её нет, релизная сборка стартует и сразу падает.
if not callable(getattr(gui_app, "run_gui", None)):
    print("FAIL  entry   ui.gui_app: нет вызываемой run_gui()")
    failures.append("ui.gui_app: нет run_gui()")
elif not callable(getattr(run_gui, "main", None)):
    print("FAIL  entry   run_gui: нет вызываемой main()")
    failures.append("run_gui: нет main()")
else:
    print("OK    entry   точка входа run_gui.main() -> ui.gui_app.run_gui()")

# Где искать ресурсы: в замороженном бандле — каталог _MEIPASS.
if getattr(sys, "frozen", False):
    base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
else:
    base = os.path.dirname(os.path.abspath(__file__))

print()
for name in DATA_FILES:
    path = os.path.join(base, name)
    if not os.path.exists(path):
        print(f"FAIL  data    {name}: не найден в {base}")
        failures.append(f"{name}: не найден в бандле")
    elif os.path.getsize(path) == 0:
        print(f"FAIL  data    {name}: файл пустой (0 байт)")
        failures.append(f"{name}: пустой файл")
    else:
        print(f"OK    data    {name} ({os.path.getsize(path)} байт)")

print()
if failures:
    print(f"SMOKE TEST FAILED: {len(failures)} проблем")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)

print("SMOKE TEST PASSED")
