"""
Консольный интерфейс: ввод от пользователя и вывод результатов.
"""

from datetime import datetime, date
import pandas as pd
import config
from logger import get_logger

logger = get_logger(__name__)


def get_user_scenario() -> tuple[date, date, str]:
    """
    Запрашивает у пользователя параметры сценария.

    Returns:
        Кортеж: (дата покупки, дата продажи, ключ сценария).
    """
    print("\n=== НАСТРОЙКА СЦЕНАРИЯ ===")

    while True:
        try:
            # 1. Дата покупки
            today = date.today().strftime("%d.%m.%Y")
            buy_str = input(
                f"Введите дату покупки (ДД.ММ.ГГГГ) [Сегодня: {today}]: "
            )

            if not buy_str.strip():
                buy_date = date.today()
            else:
                if '.' in buy_str:
                    buy_date = datetime.strptime(buy_str, "%d.%m.%Y").date()
                else:
                    buy_date = datetime.strptime(buy_str, "%Y-%m-%d").date()

            # 2. Дата продажи
            sell_str = input("Введите дату продажи (ДД.ММ.ГГГГ): ")

            if not sell_str.strip():
                print("❌ Ошибка: Дата продажи не может быть пустой!\n")
                continue

            if '.' in sell_str:
                sell_date = datetime.strptime(sell_str, "%d.%m.%Y").date()
            else:
                sell_date = datetime.strptime(sell_str, "%Y-%m-%d").date()

            if sell_date <= buy_date:
                print(
                    "❌ Ошибка: Дата продажи должна быть позже даты покупки!\n"
                )
                continue

            # 3. Выбор сценария ставки
            print("\n--- ВЫБОР СЦЕНАРИЯ КЛЮЧЕВОЙ СТАВКИ ---")
            for key, scenario in config.RATE_SCENARIOS.items():
                emoji = scenario['emoji']
                name = scenario['name']
                desc = scenario['description']
                print(f"  {key}. {emoji} {name}: {desc}")

            scenario_choice = input(
                "\nВыберите сценарий (1/2/3) [2 - Базовый]: "
            )

            if not scenario_choice.strip():
                scenario_choice = '2'

            if scenario_choice not in config.RATE_SCENARIOS:
                print("❌ Ошибка: Выберите 1, 2 или 3\n")
                continue

            selected_scenario = config.RATE_SCENARIOS[scenario_choice]

            holding_days = (sell_date - buy_date).days
            rate_change = selected_scenario['rate_change']
            scenario_name = selected_scenario['name']
            emoji = selected_scenario['emoji']

            print(f"\n✅ Принято:")
            print(
                f"   📅 Удержание: {holding_days} дней ({buy_date} -> {sell_date})"
            )
            print(
                f"   {emoji} Сценарий: {scenario_name} (ставка {rate_change:+.1f}%)"
            )

            # Логируем выбор пользователя
            logger.info(
                f"Выбор пользователя: покупка={buy_date}, "
                f"продажа={sell_date}, сценарий={scenario_name}"
            )

            return buy_date, sell_date, scenario_choice

        except ValueError as e:
            print(
                "❌ Ошибка формата. Пример: 15.10.2025 или 2025-10-15. Попробуйте снова.\n"
            )
            logger.debug(f"Ошибка ввода пользователя: {e}")


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
    scenario = config.RATE_SCENARIOS[scenario_key]
    rate_change = scenario['rate_change']
    scenario_name = scenario['name']
    scenario_emoji = scenario['emoji']

    # Сортируем по доходности за период (от большего к меньшему)
    top_reliable = res_df.sort_values(
        by='Доходность за период (%)', ascending=False
    )

    # Выводим шапку
    print("\n" + "=" * 140)
    print(
        f"🏆 РЕЗУЛЬТАТ: Удержание {holding_days} дней ({buy_date} -> {sell_date})"
    )
    print(f"🏦 Текущая ключевая ставка ЦБ: {floater_rate}%")
    print(
        f"{scenario_emoji} Выбранный сценарий: {scenario_name} (ставка {rate_change:+.1f}%)"
    )
    print(f"   {scenario['description']}")
    print("=" * 140)

    # Выводим таблицу
    print(top_reliable.to_markdown(index=False))

    # Сохраняем в файл
    output_file = config.RESULT_CSV
    res_df.to_csv(output_file, index=False, encoding='utf-8-sig')

    print(f"\n[SUCCESS] Результат сохранён в '{output_file}'")

    # Логируем итог
    logger.info(f"Результат выведен в консоль и сохранён в {output_file}")
    logger.info(f"Всего бумаг в результате: {len(res_df)}")

    # Статистика по типам
    if 'Тип' in res_df.columns:
        type_counts = res_df['Тип'].value_counts()
        logger.info(f"Статистика: {dict(type_counts)}")
