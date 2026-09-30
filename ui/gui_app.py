"""
GUI-интерфейс для NetYield MOEX на основе CustomTkinter.

Особенности:
- Современный дизайн (тёмная/светлая тема)
- Таблица с сортировкой по клику на заголовок (▲/▼)
- Поиск в реальном времени по тикеру и эмитенту
- Прогресс-бар при загрузке данных
- Экспорт в CSV
- Копирование строки в буфер обмена
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkcalendar import DateEntry
import pandas as pd
from datetime import date, datetime, timedelta
import threading
import traceback

import app_config as config
from logger import get_logger
from services.cbr_rate import get_cbr_key_rate
from services.moex_data import fetch_moex_data, prepare_data
from analysis.classification import (
    apply_coupon_classification,
    get_coupon_label,
)
from analysis.filters import apply_all_filters
from analysis.yield_calculator import (
    calculate_maturity_scenario,
    calculate_sale_scenario,
    process_coupon,
)

logger = get_logger(__name__)


# ============================================================
# НАСТРОЙКИ ТЕМЫ
# ============================================================
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# ============================================================
# ГЛАВНОЕ ОКНО
# ============================================================
class NetYieldApp(ctk.CTk):
    """Главное окно приложения."""

    def __init__(self):
        super().__init__()

        self.title("🏦 NetYield MOEX — Калькулятор доходности облигаций")
        self.geometry("1400x900")
        self.minsize(1200, 700)

        # Состояние приложения
        self.cbr_rate = 16.0
        self.df_results: pd.DataFrame | None = None
        self.df_filtered: pd.DataFrame | None = None
        self.current_scenario_key = "2"
        self.sort_column = None
        self.sort_reverse = False

        # Переменные сценария
        self.scenario_var = ctk.StringVar(value="2")

        # Настройка grid:
        # row 0 — шапка (фиксированная)
        # row 1 — панель ввода (фиксированная)
        # row 2 — таблица результатов (растягивается на всё свободное место)
        # row 3 — статус-бар (фиксированный)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=1)
        self.grid_rowconfigure(3, weight=0)

        # Построение интерфейса
        self._build_header()
        self._build_input_panel()
        self._build_results_panel()
        self._build_status_bar()

        # Загружаем ставку ЦБ в фоне
        self._load_cbr_rate_async()

    # --------------------------------------------------------
    # Построение интерфейса
    # --------------------------------------------------------
    def _build_header(self):
        """Шапка с названием и переключателем темы."""
        header = ctk.CTkFrame(self)
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        header.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            header,
            text="🏦 NetYield MOEX",
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        title.grid(row=0, column=0, sticky="w", padx=20, pady=10)

        self.theme_switch = ctk.CTkSwitch(
            header,
            text="Тёмная тема",
            command=self._toggle_theme,
            onvalue="dark",
            offvalue="light",
        )
        self.theme_switch.grid(row=0, column=1, padx=20, pady=10)
        self.theme_switch.select()

    def _create_date_entry(self, master, initial_date: date) -> DateEntry:
        """Создаёт поле ввода даты с выпадающим календарём."""
        kwargs = dict(
            master=master,
            date_pattern="dd.mm.yyyy",
            background="#1f6aa5",
            foreground="white",
            fieldbackground="#2b2b2b",
            selectbackground="#1f6aa5",
            selectforeground="white",
            normalbackground="#2b2b2b",
            normalforeground="white",
            weekendbackground="#2b2b2b",
            weekendforeground="#e08080",
            othermonthforeground="#707070",
            titlebackground="#1f6aa5",
            titleforeground="white",
            headerbackground="#2b2b2b",
            headerforeground="white",
            font=("Segoe UI", 11),
        )
        # Пробуем русскую локаль (русские названия месяцев),
        # при неудаче — стандартную
        try:
            entry = DateEntry(locale="ru_RU", **kwargs)
        except Exception:
            entry = DateEntry(**kwargs)
        entry.set_date(initial_date)
        return entry

    def _build_input_panel(self):
        """Панель ввода параметров сценария."""
        panel = ctk.CTkFrame(self)
        panel.grid(row=1, column=0, sticky="new", padx=10, pady=(5, 2))
        panel.grid_columnconfigure((0, 1, 2, 3), weight=1)

        # Заголовок
        section = ctk.CTkLabel(
            panel,
            text="⚙️ Параметры сценария",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        section.grid(
            row=0, column=0, columnspan=4, sticky="w", padx=15, pady=(10, 5)
        )

        # 📅 Дата покупки — календарь, по умолчанию сегодня
        ctk.CTkLabel(panel, text="📅 Дата покупки:").grid(
            row=1, column=0, sticky="w", padx=15, pady=5
        )
        self.buy_date_entry = self._create_date_entry(panel, date.today())
        self.buy_date_entry.grid(
            row=2, column=0, padx=15, pady=(0, 10), sticky="ew"
        )

        # 📅 Дата продажи — календарь, по умолчанию +90 дней
        ctk.CTkLabel(panel, text="📅 Дата продажи:").grid(
            row=1, column=1, sticky="w", padx=15, pady=5
        )
        self.sell_date_entry = self._create_date_entry(
            panel, date.today() + timedelta(days=90)
        )
        self.sell_date_entry.grid(
            row=2, column=1, padx=15, pady=(0, 10), sticky="ew"
        )

        # 📈 Сценарий ставки — цветные радиокнопки в столбик
        ctk.CTkLabel(panel, text="📈 Сценарий ставки:").grid(
            row=1, column=2, sticky="w", padx=15, pady=5
        )
        scenario_frame = ctk.CTkFrame(panel, fg_color="transparent")
        scenario_frame.grid(
            row=2, column=2, padx=15, pady=(0, 10), sticky="ew"
        )
        scenario_frame.grid_columnconfigure(0, weight=1)

        for i, (key, scenario) in enumerate(config.RATE_SCENARIOS.items()):
            ctk.CTkRadioButton(
                scenario_frame,
                text=scenario['gui_label'],
                variable=self.scenario_var,
                value=key,
                fg_color=scenario['color'],
                hover_color=scenario['color_hover'],
                text_color=scenario['text_color'],
                font=ctk.CTkFont(size=12, weight="bold"),
            ).grid(row=i, column=0, padx=5, pady=3, sticky="w")

        # Кнопка "Рассчитать"
        self.calc_button = ctk.CTkButton(
            panel,
            text="🚀 Рассчитать",
            command=self._on_calculate,
            font=ctk.CTkFont(size=14, weight="bold"),
            height=40,
        )
        self.calc_button.grid(
            row=1, column=3, rowspan=2, padx=15, pady=5, sticky="ew"
        )

    def _build_results_panel(self):
        """Панель результатов: поиск + таблица + действия."""
        panel = ctk.CTkFrame(self)
        panel.grid(row=2, column=0, sticky="nsew", padx=10, pady=(2, 5))
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(2, weight=1)

        # Панель поиска и действий
        toolbar = ctk.CTkFrame(panel, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        toolbar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(toolbar, text="🔍 Поиск:").grid(
            row=0, column=0, padx=(5, 10)
        )

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._apply_search())

        self.search_entry = ctk.CTkEntry(
            toolbar,
            textvariable=self.search_var,
            placeholder_text="Введите тикер или название эмитента...",
            width=300,
        )
        self.search_entry.grid(row=0, column=1, sticky="ew", padx=5)

        ctk.CTkButton(
            toolbar, text="Очистить", width=90, command=self._clear_search
        ).grid(row=0, column=2, padx=5)

        ctk.CTkButton(
            toolbar, text="💾 Экспорт CSV", width=120, command=self._export_csv
        ).grid(row=0, column=3, padx=5)

        # Счётчик строк
        self.rows_label = ctk.CTkLabel(
            toolbar, text="Строк: 0", font=ctk.CTkFont(size=12)
        )
        self.rows_label.grid(row=0, column=4, padx=(15, 5))

        # Подсказка по сортировке
        hint = ctk.CTkLabel(
            panel,
            text="💡 Нажмите на заголовок столбца для сортировки (▲/▼)",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        )
        hint.grid(row=1, column=0, sticky="w", padx=15, pady=(0, 5))

        # Таблица результатов
        table_frame = ctk.CTkFrame(panel)
        table_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)

        self._build_treeview(table_frame)

        # Прогресс-бар
        self.progress = ctk.CTkProgressBar(panel, mode="indeterminate")
        self.progress.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))

    def _build_treeview(self, parent):
        """Создаёт Treeview с кастомной сортировкой."""
        style = ttk.Style()
        style.theme_use("clam")

        # Настраиваем стиль под тёмную тему
        bg_color = "#2b2b2b"
        fg_color = "#e0e0e0"
        header_bg = "#1f6aa5"
        header_fg = "white"
        selected_bg = "#1f6aa5"
        selected_fg = "white"
        row_even = "#2b2b2b"
        row_odd = "#333333"

        style.configure(
            "Treeview",
            background=bg_color,
            foreground=fg_color,
            fieldbackground=bg_color,
            rowheight=28,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Treeview.Heading",
            background=header_bg,
            foreground=header_fg,
            font=("Segoe UI", 10, "bold"),
            relief="flat",
        )
        style.map(
            "Treeview",
            background=[("selected", selected_bg)],
            foreground=[("selected", selected_fg)],
        )
        style.map(
            "Treeview.Heading",
            background=[("active", "#1a5a8a")],
        )

        # Чередование строк
        style.configure("Treeview", rowheight=28)

        # Контейнер с прокруткой
        tree_container = tk.Frame(parent, bg=bg_color)
        tree_container.grid(row=0, column=0, sticky="nsew")
        tree_container.grid_columnconfigure(0, weight=1)
        tree_container.grid_rowconfigure(0, weight=1)

        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        # Столбцы таблицы
        columns = (
            "secid",
            "type",
            "issuer",
            "coupon_type",
            "price",
            "coupon",
            "maturity",
            "offer",
            "status",
            "days",
            "trades",
            "turnover",
            "net_income",
            "period_yield",
            "annual_yield",
        )

        self.tree = ttk.Treeview(
            tree_container,
            columns=columns,
            show="headings",
            selectmode="browse",
        )

        # Заголовки столбцов
        headings = {
            "secid": ("Тикер", 120),
            "type": ("Тип", 80),
            "issuer": ("Эмитент", 150),
            "coupon_type": ("Тип купона", 120),
            "price": ("Цена (%)", 90),
            "coupon": ("Купон (%)", 90),
            "maturity": ("Погашение", 100),
            "offer": ("Оферта", 100),
            "status": ("Статус", 100),
            "days": ("Дней", 60),
            "trades": ("Сделок", 70),
            "turnover": ("Оборот (тыс)", 100),
            "net_income": ("Чист. доход (₽)", 120),
            "period_yield": ("Доход. за период (%)", 150),
            "annual_yield": ("Годовая доход. (%)", 150),
        }

        for col, (title, width) in headings.items():
            self.tree.heading(
                col,
                text=title,
                command=lambda c=col: self._sort_by_column(c),
            )
            self.tree.column(col, width=width, anchor="w")

        # Скроллбары
        vsb = ttk.Scrollbar(
            tree_container, orient="vertical", command=self.tree.yview
        )
        hsb = ttk.Scrollbar(
            tree_container, orient="horizontal", command=self.tree.xview
        )
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        # Двойной клик — копирование строки
        self.tree.bind("<Double-1>", self._on_double_click)

    def _build_status_bar(self):
        """Статус-бар внизу."""
        status = ctk.CTkFrame(self, height=30)
        status.grid(row=3, column=0, sticky="ew", padx=10, pady=(5, 10))
        status.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(
            status,
            text="Готов к работе",
            font=ctk.CTkFont(size=11),
            anchor="w",
        )
        self.status_label.grid(row=0, column=0, sticky="ew", padx=15, pady=5)

    # --------------------------------------------------------
    # Загрузка ставки ЦБ
    # --------------------------------------------------------
    def _load_cbr_rate_async(self):
        """Загружает ставку ЦБ в фоновом потоке."""
        self.status_label.configure(
            text="⏳ Загрузка ключевой ставки ЦБ РФ..."
        )

        def task():
            try:
                rate = get_cbr_key_rate(
                    fallback_rate=config.FLOATING_COUPON_RATE
                )
                self.cbr_rate = rate
                self.after(
                    0,
                    lambda: self.status_label.configure(
                        text=f"✅ Ключевая ставка ЦБ РФ: {rate}%"
                    ),
                )
            except Exception as e:
                logger.error(f"Ошибка при загрузке ставки ЦБ: {e}")
                self.after(
                    0,
                    lambda: self.status_label.configure(
                        text=f"⚠️ Не удалось загрузить ставку ЦБ. Используется: {self.cbr_rate}%"
                    ),
                )

        threading.Thread(target=task, daemon=True).start()

    # --------------------------------------------------------
    # Основной расчёт
    # --------------------------------------------------------
    def _on_calculate(self):
        """Запускает расчёт в фоновом потоке."""
        # Читаем даты напрямую из календарей
        try:
            buy_date = self.buy_date_entry.get_date()
            sell_date = self.sell_date_entry.get_date()

            if sell_date <= buy_date:
                messagebox.showerror(
                    "Ошибка",
                    "Дата продажи должна быть позже даты покупки!",
                )
                return

        except Exception as e:
            messagebox.showerror(
                "Ошибка",
                f"Не удалось прочитать даты.\n{e}",
            )
            return

        scenario_key = self.scenario_var.get()

        # Блокируем кнопку и показываем прогресс
        self.calc_button.configure(state="disabled", text="⏳ Расчёт...")
        self.progress.start()
        self.status_label.configure(text="🔄 Загрузка данных с Мосбиржи...")

        def task():
            try:
                df = self._run_analysis(buy_date, sell_date, scenario_key)
                self.after(0, lambda: self._show_results(df, scenario_key))
            except Exception as e:
                logger.error(
                    f"Ошибка при расчёте: {e}\n{traceback.format_exc()}"
                )
                self.after(
                    0,
                    lambda: messagebox.showerror(
                        "Ошибка расчёта",
                        f"{e}\n\nПодробности в логе net_yield.log",
                    ),
                )
            finally:
                self.after(0, self._finish_calculation)

        threading.Thread(target=task, daemon=True).start()

    def _finish_calculation(self):
        """Завершает расчёт — восстанавливает UI."""
        self.progress.stop()
        self.calc_button.configure(state="normal", text="🚀 Рассчитать")

    def _run_analysis(
        self, buy_date, sell_date, scenario_key: str
    ) -> pd.DataFrame:
        """Выполняет полный цикл анализа."""
        # Загрузка данных
        df = fetch_moex_data()
        if df is None or df.empty:
            raise RuntimeError("Не удалось получить данные с Мосбиржи")

        # Подготовка
        df = prepare_data(df)
        df = apply_coupon_classification(df)

        # Фильтрация
        buy_ts = pd.Timestamp(buy_date)
        sell_ts = pd.Timestamp(sell_date)
        df = apply_all_filters(df, buy_ts, sell_ts)

        if df.empty:
            raise RuntimeError("По заданным фильтрам бумаги не найдены")

        # Параметры сценария
        holding_days = (sell_date - buy_date).days
        scenario = config.RATE_SCENARIOS[scenario_key]
        rate_change = scenario["rate_change"]

        # Расчёт
        results = []
        for _, row in df.iterrows():
            try:
                facevalue = row["FACEVALUE"]
                current_price = row["PRICE_PCT"]
                is_ofz = row["IS_OFZ"]
                mat_date = row["MATDATE"]
                secid = row["SECID"]
                coupon_class = row["COUPON_CLASS"]
                duration_days = row["DURATION_DAYS"]

                if (
                    pd.isna(current_price)
                    or pd.isna(facevalue)
                    or current_price <= 0
                ):
                    continue

                coupon_pct = process_coupon(
                    row["COUPONPERCENT"], coupon_class, self.cbr_rate
                )
                if coupon_pct is None:
                    continue

                purchase_price_rub = facevalue * current_price / 100

                matures_within_period = (
                    pd.notna(mat_date)
                    and mat_date <= sell_ts
                    and mat_date > buy_ts
                )

                if matures_within_period:
                    actual_holding_days = (mat_date.date() - buy_date).days
                    if actual_holding_days <= 0:
                        continue

                    calc = calculate_maturity_scenario(
                        facevalue=facevalue,
                        purchase_price_rub=purchase_price_rub,
                        coupon_pct=coupon_pct,
                        actual_holding_days=actual_holding_days,
                        is_ofz=is_ofz,
                    )
                    mat_date_str = mat_date.strftime("%d.%m.%Y")
                else:
                    calc = calculate_sale_scenario(
                        facevalue=facevalue,
                        purchase_price_rub=purchase_price_rub,
                        current_price_pct=current_price,
                        coupon_pct=coupon_pct,
                        holding_days=holding_days,
                        is_ofz=is_ofz,
                        duration_days=duration_days,
                        rate_change_pct=rate_change,
                    )
                    mat_date_str = (
                        mat_date.strftime("%d.%m.%Y")
                        if pd.notna(mat_date)
                        else "Нет"
                    )

                offer_date_str = (
                    row["OFFERDATE"].strftime("%d.%m.%Y")
                    if pd.notna(row["OFFERDATE"])
                    else "Нет"
                )

                results.append(
                    {
                        "Тикер": secid,
                        "Тип": "ОФЗ" if is_ofz else "Корпорат",
                        "Эмитент": row["SHORTNAME"],
                        "Тип купона": get_coupon_label(coupon_class),
                        "Цена (%)": round(current_price, 2),
                        "Купон (%)": round(coupon_pct, 2),
                        "Погашение": mat_date_str,
                        "Оферта": offer_date_str,
                        "Статус": calc["status"],
                        "Дней": calc["effective_days"],
                        "Сделок": int(row["NUMTRADES"]),
                        "Оборот (тыс)": round(row["VALUE"] / 1000, 1),
                        "Чист. доход (₽)": round(calc["net_profit_rub"], 2),
                        "Доход. за период (%)": round(
                            calc["horizon_return_pct"], 2
                        ),
                        "Годовая доход. (%)": round(
                            calc["annualized_return"], 2
                        ),
                    }
                )
            except Exception as e:
                logger.debug(f"Пропуск {row.get('SECID', '?')}: {e}")
                continue

        return pd.DataFrame(results)

    def _show_results(self, df: pd.DataFrame, scenario_key: str):
        """Отображает результаты в таблице."""
        self.df_results = df
        self.df_filtered = df.copy()

        scenario = config.RATE_SCENARIOS[scenario_key]

        # Очищаем таблицу
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Заполняем таблицу
        columns = list(df.columns)
        for _, row in df.iterrows():
            values = tuple(
                row[col] if pd.notna(row[col]) else "" for col in columns
            )
            self.tree.insert("", "end", values=values)

        # Применяем текущий поиск
        self._apply_search()

        # Обновляем статус
        self.status_label.configure(
            text=f"✅ {scenario['emoji']} {scenario['name']} | "
            f"Найдено облигаций: {len(df)}"
        )

    # --------------------------------------------------------
    # Сортировка
    # --------------------------------------------------------
    def _sort_by_column(self, col: str):
        """Сортирует таблицу по указанному столбцу."""
        if self.sort_column == col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = col
            self.sort_reverse = False

        # Получаем текущие данные
        data = []
        for item in self.tree.get_children():
            values = self.tree.item(item, "values")
            idx = self.tree["columns"].index(col)
            data.append((values[idx], item))

        # Пытаемся преобразовать к числам для числовой сортировки
        try:
            data.sort(
                key=lambda x: (
                    float(x[0]) if x[0] not in ("", "Нет") else -999999
                ),
                reverse=self.sort_reverse,
            )
        except (ValueError, TypeError):
            data.sort(key=lambda x: str(x[0]), reverse=self.sort_reverse)

        # Переставляем элементы
        for index, (_, item) in enumerate(data):
            self.tree.move(item, "", index)

        # Обновляем заголовки с индикатором сортировки
        for c in self.tree["columns"]:
            original_title = {
                "secid": "Тикер",
                "type": "Тип",
                "issuer": "Эмитент",
                "coupon_type": "Тип купона",
                "price": "Цена (%)",
                "coupon": "Купон (%)",
                "maturity": "Погашение",
                "offer": "Оферта",
                "status": "Статус",
                "days": "Дней",
                "trades": "Сделок",
                "turnover": "Оборот (тыс)",
                "net_income": "Чист. доход (₽)",
                "period_yield": "Доход. за период (%)",
                "annual_yield": "Годовая доход. (%)",
            }.get(c, c)

            if c == col:
                arrow = " ▼" if self.sort_reverse else " ▲"
                self.tree.heading(c, text=original_title + arrow)
            else:
                self.tree.heading(c, text=original_title)

    # --------------------------------------------------------
    # Поиск
    # --------------------------------------------------------
    def _apply_search(self):
        """Фильтрует таблицу по поисковому запросу."""
        query = self.search_var.get().strip().lower()

        if self.df_results is None:
            return

        if not query:
            self.df_filtered = self.df_results.copy()
        else:
            mask = self.df_results["Тикер"].str.lower().str.contains(
                query, na=False
            ) | self.df_results["Эмитент"].str.lower().str.contains(
                query, na=False
            )
            self.df_filtered = self.df_results[mask].copy()

        # Очищаем и перерисовываем таблицу
        for item in self.tree.get_children():
            self.tree.delete(item)

        columns = list(self.df_filtered.columns)
        for _, row in self.df_filtered.iterrows():
            values = tuple(
                row[col] if pd.notna(row[col]) else "" for col in columns
            )
            self.tree.insert("", "end", values=values)

        self.rows_label.configure(
            text=f"Строк: {len(self.df_filtered)} / {len(self.df_results)}"
        )

    def _clear_search(self):
        """Очищает поле поиска."""
        self.search_var.set("")

    # --------------------------------------------------------
    # Вспомогательные функции
    # --------------------------------------------------------
    def _toggle_theme(self):
        """Переключает тему."""
        mode = self.theme_switch.get()
        ctk.set_appearance_mode(mode)
        self.theme_switch.configure(
            text="Тёмная тема" if mode == "dark" else "Светлая тема"
        )

    def _export_csv(self):
        """Экспортирует результаты в CSV."""
        if self.df_filtered is None or self.df_filtered.empty:
            messagebox.showinfo("Информация", "Нет данных для экспорта")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV файлы", "*.csv"), ("Все файлы", "*.*")],
            initialfile=config.RESULT_CSV,
            title="Сохранить результат",
        )

        if file_path:
            try:
                self.df_filtered.to_csv(
                    file_path, index=False, encoding="utf-8-sig"
                )
                self.status_label.configure(
                    text=f"💾 Экспортировано: {file_path}"
                )
                messagebox.showinfo(
                    "Готово",
                    f"Данные сохранены в:\n{file_path}",
                )
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось сохранить:\n{e}")

    def _on_double_click(self, event):
        """Копирует выбранную строку в буфер обмена."""
        item = self.tree.selection()
        if not item:
            return

        values = self.tree.item(item[0], "values")
        text = " | ".join(str(v) for v in values)

        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_label.configure(
            text=f"📋 Скопировано: {values[0]} — {values[2]}"
        )


# ============================================================
# Точка входа
# ============================================================
def run_gui():
    """Запускает GUI-приложение."""
    app = NetYieldApp()
    app.mainloop()


if __name__ == "__main__":
    run_gui()
