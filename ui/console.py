"""
Консольный интерфейс: ввод от пользователя и вывод результатов.
"""

from datetime import date, datetime

import pandas as pd

import app_config as config
from analysis.result_schema import YIELD_COLUMN
from logger import get_logger

logger = get_logger(__name__)

DEFAULT_SCENARIO = '2'


def _parse_date(raw: str) -> date:
    """Парсит дату в формате ДД.ММ.ГГГГ или ГГГГ-ММ-ДД."""
    fmt = "%d.%m.%Y" if '.' in raw else "%Y-%m-%d"
    return datetime.strptime(raw, fmt).date()


def get_user_scenario() -> tuple[date, date, str]:
    """
    Запрашивает у пользователя параметры сценария.

    Returns:
        Кортеж: (дата покупки, дата продажи, ключ сценария).
    """
    print("\n=== НАСТРОЙКА СЦЕНАРИЯ ===")

    while True:
        try:
            buy_date = _ask_buy_date()
            sell_date = _ask_sell_date(buy_date)
        except ValueError as e:
            print(f"❌ Ошибка формата. Пример: 15.10.2025 или 2025-10-15. ({e})\n")
            logger.debug(f"Ошибка ввода пользователя: {e}")
            continue

        if sell_date is None:
            continue

        scenario_key = _ask_scenario(buy_date, sell_date)
        if scenario_key is None:
            continue

        logger.info(
            f"Выбор пользователя: покупка={buy_date}, "
            f"продажа={sell_date}, сценарий={scenario_key}"
        )
        return buy_date, sell_date, scenario_key


def _ask_buy_date() -> date:
    """Спрашивает дату покупки, по умолчанию — сегодня."""
    today = date.today().strftime("%d.%m.%Y")
    buy_str = input(f"Введите дату покупки (ДД.ММ.ГГГГ) [Сегодня: {today}]: ")

    if not buy_str.strip():
        return date.today()
    return _parse_date(buy_str.strip())


def _ask_sell_date(buy_date: date) -> date | None:
    """Спрашивает дату продажи. None — ввод неверный, сценарий сначала."""
    sell_str = input("Введите дату продажи (ДД.ММ.ГГГГ): ").strip()

    if not sell_str:
        print("❌ Ошибка: Дата продажи не может быть пустой!\n")
        return None

    sell_date = _parse_date(sell_str)
    if sell_date <= buy_date:
        print("❌ Ошибка: Дата продажи должна быть позже даты покупки!\n")
        return None

    return sell_date


def _ask_scenario(buy_date: date, sell_date: date) -> str | None:
    """Печатает сценарии и спрашивает номер. None — неверный выбор."""
    print("\n--- ВЫБОР СЦЕНАРИЯ КЛЮЧЕВОЙ СТАВКИ ---")
    for key, scenario in config.RATE_SCENARIOS.items():
        print(
            f"  {key}. {scenario['emoji']} {scenario['name']}: "
            f"{scenario['description']}"
        )

    choices = "/".join(config.RATE_SCENARIOS)
    choice = input(
        f"\nВыберите сценарий ({choices}) "
        f"[{DEFAULT_SCENARIO} - Базовый]: "
    ).strip()

    if not choice:
        choice = DEFAULT_SCENARIO

    if choice not in config.RATE_SCENARIOS:
        print(f"❌ Ошибка: Выберите один из вариантов: {choices}\n")
        return None

    scenario = config.get_scenario(choice)
    holding_days = (sell_date - buy_date).days

    print("\n✅ Принято:")
    print(f"   📅 Удержание: {holding_days} дней ({buy_date} -> {sell_date})")
    print(
        f"   {scenario['emoji']} Сценарий: {scenario['name']} "
        f"(ставка {scenario['rate_change']:+.1f}%)"
    )
    return choice


def print_results(
    res_df: pd.DataFrame,
    holding_days: int,
    buy_date: date,
    sell_date: date,
    floater_rate: float,
    scenario_key: str,
):
    """
    Выводит таблицу результатов в консоль и сохраняет в CSV-файл.

    Args:
        res_df: DataFrame с рассчитанными результатами.
        holding_days: Период владения в днях.
        buy_date: Дата покупки.
        sell_date: Дата продажи.
        floater_rate: Текущая ключевая ставка ЦБ.
        scenario_key: Ключ выбранного сценария.
    """
    scenario = config.get_scenario(scenario_key)

    # Сортируем по доходности за период (от большего к меньшему)
    top_reliable = res_df.sort_values(by=YIELD_COLUMN, ascending=False)

    print("\n" + "=" * 140)
    print(
        f"🏆 РЕЗУЛЬТАТ: Удержание {holding_days} дней ({buy_date} -> {sell_date})"
    )
    print(f"🏦 Текущая ключевая ставка ЦБ: {floater_rate}%")
    print(
        f"{scenario['emoji']} Выбранный сценарий: {scenario['name']} "
        f"(ставка {scenario['rate_change']:+.1f}%)"
    )
    print(f"   {scenario['description']}")
    print("=" * 140)

    print(top_reliable.to_markdown(index=False))

    output_file = config.RESULT_CSV
    res_df.to_csv(output_file, index=False, encoding='utf-8-sig')

    print(f"\n[SUCCESS] Результат сохранён в '{output_file}'")

    logger.info(f"Результат выведен в консоль и сохранён в {output_file}")
    logger.info(f"Всего бумаг в результате: {len(res_df)}")

    # Статистика по типам
    if 'Тип' in res_df.columns:
        counts = res_df['Тип'].value_counts()
        logger.info(f"Статистика: {dict(zip(counts.index, counts.astype(int)))}")