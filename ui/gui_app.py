"""
GUI-интерфейс для NetYield MOEX на основе CustomTkinter.

Особенности:
- Современный дизайн (тёмная/светлая тема)
- Таблица с сортировкой по клику на заголовок (▲/▼)
- Поиск в реальном времени по тикеру и эмитенту
- Прогресс-бар при загрузке данных
- Экспорт в CSV
- Копирование строки в буфер обмена

Расчёты живут в analysis.pipeline — здесь только интерфейс.
"""

import customtkinter as ctk
import tkinter as tk
from datetime import date, timedelta
from threading import Thread
from tkinter import filedialog, messagebox, ttk
from tkcalendar import DateEntry
import os
import traceback

import pandas as pd

import app_config as config
from analysis.pipeline import AnalysisError, run_analysis
from analysis.result_schema import RESULT_COLUMNS
from logger import get_logger
from services.cbr_rate import get_cbr_key_rate

logger = get_logger(__name__)


# ============================================================
# НАСТРОЙКИ ТЕМЫ
# ============================================================
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Цвета таблицы. Дублируют значения из _create_date_entry — держать вместе.
BG = "#2b2b2b"
FG = "#e0e0e0"
ACCENT = "#1f6aa5"
ACCENT_ACTIVE = "#1a5a8a"
TEXT_DIM = "#707070"
TEXT_WARN = "#e08080"

SEARCH_COLUMNS = ("Тикер", "Эмитент")


# ============================================================
# ГЛАВНОЕ ОКНО
# ============================================================
class NetYieldApp(ctk.CTk):
    """Главное окно приложения."""

    def __init__(self):
        super().__init__()

        self.title("🏦 NetYield MOEX — Калькулятор доходности облигаций")
        self._set_app_icon()
        self.geometry("1400x900")
        self.minsize(1200, 700)

        # Состояние приложения
        self.cbr_rate = config.FLOATING_COUPON_RATE
        self.df_results = None
        self.df_filtered = None
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
            background=ACCENT,
            foreground="white",
            fieldbackground=BG,
            selectbackground=ACCENT,
            selectforeground="white",
            normalbackground=BG,
            normalforeground="white",
            weekendbackground=BG,
            weekendforeground=TEXT_WARN,
            othermonthforeground=TEXT_DIM,
            titlebackground=ACCENT,
            titleforeground="white",
            headerbackground=BG,
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

    def _setup_treeview_style(self):
        """Настраивает вид Treeview под тёмную тему."""
        style = ttk.Style()
        style.theme_use("clam")

        style.configure(
            "Treeview",
            background=BG,
            foreground=FG,
            fieldbackground=BG,
            rowheight=28,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Treeview.Heading",
            background=ACCENT,
            foreground="white",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
        )
        style.map(
            "Treeview",
            background=[("selected", ACCENT)],
            foreground=[("selected", "white")],
        )
        style.map(
            "Treeview.Heading",
            background=[("active", ACCENT_ACTIVE)],
        )

    def _build_treeview(self, parent):
        """Создаёт Treeview с кастомной сортировкой.

        Состав столбцов берётся из analysis.result_schema — там же живут
        подписи и ширины, поэтому рассинхрона с расчётом быть не может.
        """
        self._setup_treeview_style()
        self.column_defs = {col.key: col for col in RESULT_COLUMNS}

        # Контейнер со скроллбарами
        tree_container = tk.Frame(parent, bg=BG)
        tree_container.grid(row=0, column=0, sticky="nsew")
        tree_container.grid_columnconfigure(0, weight=1)
        tree_container.grid_rowconfigure(0, weight=1)

        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            tree_container,
            columns=list(self.column_defs),
            show="headings",
            selectmode="browse",
        )

        for key, col in self.column_defs.items():
            self.tree.heading(
                key,
                text=key,
                command=lambda c=key: self._sort_by_column(c),
            )
            self.tree.column(key, width=col.width, anchor="w")

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
    # Потоки и расчёт
    # --------------------------------------------------------
    def _run_in_background(self, work, on_error):
        """Выполняет work() вне GUI-потока, результат отдаёт в GUI-поток.

        Args:
            work: Функция без аргументов. Выполняется в фоне и возвращает
                функцию, которую надо вызвать в GUI-потоке (или None).
            on_error: Обработчик исключения, получает текст ошибки.
        """

        def wrapper():
            try:
                action = work()
                if action is not None:
                    self.after(0, action)
            except AnalysisError as e:
                # Ошибка данных: показываем текст как есть, без трейсбека
                logger.warning(f"Анализ не выполнен: {e}")
                self.after(0, lambda: on_error(str(e)))
            except Exception as e:
                logger.error(
                    f"Ошибка в фоновом потоке: {e}\n{traceback.format_exc()}"
                )
                self.after(0, lambda: on_error(str(e)))

        Thread(target=wrapper, daemon=True).start()

    def _load_cbr_rate_async(self):
        """Загружает ставку ЦБ в фоновом потоке."""
        self.status_label.configure(
            text="⏳ Загрузка ключевой ставки ЦБ РФ..."
        )

        def fetch_rate():
            self.cbr_rate = get_cbr_key_rate(
                fallback_rate=config.FLOATING_COUPON_RATE
            )
            return lambda: self._show_cbr_rate(self.cbr_rate)

        self._run_in_background(fetch_rate, self._show_cbr_rate_error)

    def _show_cbr_rate(self, rate: float):
        """Показывает загруженную ставку в статус-баре."""
        self.status_label.configure(text=f"✅ Ключевая ставка ЦБ РФ: {rate}%")

    def _show_cbr_rate_error(self, message: str):
        """Ставка не загрузилась — предупреждаем и работаем с резервной."""
        logger.debug(f"Ставка ЦБ не загружена: {message}")
        self.status_label.configure(
            text=(
                f"⚠️ Не удалось загрузить ставку ЦБ. "
                f"Используется: {self.cbr_rate}%"
            )
        )

    def _on_calculate(self):
        """Запускает расчёт в фоновом потоке."""
        dates = self._read_dates()
        if dates is None:
            return
        buy_date, sell_date = dates

        scenario_key = self.scenario_var.get()

        # Блокируем кнопку и показываем прогресс
        self.calc_button.configure(state="disabled", text="⏳ Расчёт...")
        self.progress.start()
        self.status_label.configure(text="🔄 Загрузка данных с Мосбиржи...")

        def calculate():
            df = run_analysis(
                buy_date, sell_date, scenario_key, self.cbr_rate
            )
            return lambda: self._show_results(df, scenario_key)

        self._run_in_background(calculate, self._show_calculation_error)

    def _read_dates(self) -> tuple[date, date] | None:
        """Читает даты из календарей. None — ввод неверный, не считаем."""
        try:
            buy_date = self.buy_date_entry.get_date()
            sell_date = self.sell_date_entry.get_date()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось прочитать даты.\n{e}")
            return None

        if sell_date <= buy_date:
            messagebox.showerror(
                "Ошибка",
                "Дата продажи должна быть позже даты покупки!",
            )
            return None

        return buy_date, sell_date

    def _show_calculation_error(self, message: str):
        """Показывает ошибку расчёта и восстанавливает UI."""
        self._finish_calculation()
        messagebox.showerror(
            "Ошибка расчёта",
            f"{message}\n\nПодробности в логе {os.path.basename(config.LOG_FILE)}",
        )

    def _finish_calculation(self):
        """Завершает расчёт — восстанавливает UI."""
        self.progress.stop()
        self.calc_button.configure(state="normal", text="🚀 Рассчитать")

    # --------------------------------------------------------
    # Отображение результатов
    # --------------------------------------------------------
    def _show_results(self, df, scenario_key: str):
        """Отображает результаты в таблице."""
        self.df_results = df
        self.df_filtered = df

        scenario = config.get_scenario(scenario_key)
        self._apply_search()
        self.status_label.configure(
            text=f"✅ {scenario['emoji']} {scenario['name']} | "
            f"Найдено облигаций: {len(df)}"
        )

    def _fill_tree(self, df):
        """Полностью перерисовывает таблицу по DataFrame."""
        for item in self.tree.get_children():
            self.tree.delete(item)

        columns = list(df.columns)
        for _, row in df.iterrows():
            values = tuple(
                row[col] if pd.notna(row[col]) else "" for col in columns
            )
            self.tree.insert("", "end", values=values)

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

        index = list(self.tree["columns"]).index(col)
        data = [
            (self.tree.item(item, "values")[index], item)
            for item in self.tree.get_children()
        ]

        # Тип столбца известен из схемы: числовые сортируем как числа,
        # остальные — как строки, без try/except на каждом значении.
        if self.column_defs[col].numeric:
            key = lambda pair: (
                float(pair[0]) if pair[0] not in ("", "Нет") else -999999
            )
        else:
            key = lambda pair: str(pair[0])

        data.sort(key=key, reverse=self.sort_reverse)

        for position, (_, item) in enumerate(data):
            self.tree.move(item, "", position)

        # Обновляем заголовки с индикатором сортировки
        for column in self.tree["columns"]:
            title = column
            if column == col:
                title += " ▼" if self.sort_reverse else " ▲"
            self.tree.heading(column, text=title)

    # --------------------------------------------------------
    # Поиск
    # --------------------------------------------------------
    def _apply_search(self):
        """Фильтрует таблицу по поисковому запросу и перерисовывает её."""
        if self.df_results is None:
            return

        query = self.search_var.get().strip().lower()
        if not query:
            self.df_filtered = self.df_results
        else:
            mask = None
            for column in SEARCH_COLUMNS:
                hit = (
                    self.df_results[column]
                    .str.lower()
                    .str.contains(query, na=False)
                )
                mask = hit if mask is None else (mask | hit)
            self.df_filtered = self.df_results[mask]

        self._fill_tree(self.df_filtered)
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
        mode = str(self.theme_switch.get())
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

        if not file_path:
            return

        try:
            self.df_filtered.to_csv(
                file_path, index=False, encoding="utf-8-sig"
            )
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить:\n{e}")
            return

        self.status_label.configure(text=f"💾 Экспортировано: {file_path}")
        messagebox.showinfo("Готово", f"Данные сохранены в:\n{file_path}")

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

    def _set_app_icon(self):
        """Устанавливает иконку окна: .ico на Windows, .png на Linux/Wine."""
        base = config.BASE_DIR

        try:
            ico = os.path.join(base, "app_icon.ico")
            png = os.path.join(base, "app_icon.png")
            if os.path.exists(ico):
                self.iconbitmap(ico)
            if os.path.exists(png):
                # Держим ссылку, чтобы PhotoImage не собрался сборщиком мусора
                self._icon_img = tk.PhotoImage(file=png)
                self.iconphoto(True, self._icon_img)
        except Exception as e:
            logger.debug(f"Не удалось установить иконку окна: {e}")


# ============================================================
# Точка входа
# ============================================================
def run_gui():
    """Запускает GUI-приложение."""
    app = NetYieldApp()
    app.mainloop()


if __name__ == "__main__":
    run_gui()