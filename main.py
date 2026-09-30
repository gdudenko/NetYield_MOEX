"""
NetYield MOEX — калькулятор доходности облигаций.
"""

import pandas as pd

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
from ui.console import get_user_scenario, print_results

logger = get_logger(__name__)


def analyze_reliable_bonds(
    buy_date, sell_date, scenario_key: str, floater_rate: float
):
    """Основная логика анализа облигаций."""

    logger.info("=" * 60)
    logger.info("Запуск анализа облигаций")
    logger.info(f"Период: {buy_date} → {sell_date}")
    logger.info(f"Сценарий: {config.RATE_SCENARIOS[scenario_key]['name']}")
    logger.info("=" * 60)

    # 1. Получаем данные
    df = fetch_moex_data()
    if df is None or df.empty:
        logger.error("Не удалось получить данные для анализа.")
        return

    holding_days = (sell_date - buy_date).days
    scenario = config.RATE_SCENARIOS[scenario_key]
    rate_change = scenario['rate_change']

    # 2. Подготавливаем данные
    df = prepare_data(df)

    # 3. Классифицируем типы купонов
    df = apply_coupon_classification(df)

    # 4. Применяем фильтры
    buy_ts = pd.Timestamp(buy_date)
    sell_ts = pd.Timestamp(sell_date)

    df_reliable = apply_all_filters(df, buy_ts, sell_ts)

    if df_reliable.empty:
        logger.warning("По заданным фильтрам бумаги не найдены.")
        return

    # 5. Рассчитываем доходность
    logger.info("Рассчитываю доходность для каждой бумаги...")
    results = []
    errors_count = 0

    for _, row in df_reliable.iterrows():
        try:
            facevalue = row['FACEVALUE']
            current_price = row['PRICE_PCT']
            is_ofz = row['IS_OFZ']
            mat_date = row['MATDATE']
            secid = row['SECID']
            coupon_class = row['COUPON_CLASS']
            duration_days = row['DURATION_DAYS']

            if (
                pd.isna(current_price)
                or pd.isna(facevalue)
                or current_price <= 0
            ):
                logger.debug(
                    f"{secid}: пропущена (некорректная цена или номинал)"
                )
                continue

            coupon_pct = process_coupon(
                row['COUPONPERCENT'], coupon_class, floater_rate
            )
            if coupon_pct is None:
                logger.debug(f"{secid}: пропущена (купон < 1% и не флоатер)")
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

                calc_result = calculate_maturity_scenario(
                    facevalue=facevalue,
                    purchase_price_rub=purchase_price_rub,
                    coupon_pct=coupon_pct,
                    actual_holding_days=actual_holding_days,
                    is_ofz=is_ofz,
                )
                mat_date_str = mat_date.strftime('%d.%m.%Y')

            else:
                calc_result = calculate_sale_scenario(
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
                    mat_date.strftime('%d.%m.%Y')
                    if pd.notna(mat_date)
                    else 'Нет'
                )

            offer_date_str = (
                row['OFFERDATE'].strftime('%d.%m.%Y')
                if pd.notna(row['OFFERDATE'])
                else 'Нет'
            )

            results.append(
                {
                    'Тикер': secid,
                    'Тип': 'ОФЗ' if is_ofz else 'Корпорат',
                    'Эмитент': row['SHORTNAME'],
                    'Тип купона': get_coupon_label(coupon_class),
                    'Тек. Цена (%)': current_price,
                    'Купон (%)': coupon_pct,
                    'Дата погашения': mat_date_str,
                    'Дата оферты': offer_date_str,
                    'Статус': calc_result['status'],
                    'Дней': calc_result['effective_days'],
                    'Сделок': int(row['NUMTRADES']),
                    'Оборот (тыс.руб)': round(row['VALUE'] / 1000, 0),
                    'Чист. доход (руб)': round(
                        calc_result['net_profit_rub'], 2
                    ),
                    'Доходность за период (%)': round(
                        calc_result['horizon_return_pct'], 2
                    ),
                    'Годовая доходность (%)': round(
                        calc_result['annualized_return'], 2
                    ),
                }
            )

        except Exception as e:
            errors_count += 1
            from error_handler import log_calculation_error

            log_calculation_error(
                e,
                bond_id=row.get('SECID', 'unknown'),
                calculation_type=(
                    'maturity' if matures_within_period else 'sale'
                ),
                input_data={
                    'current_price': current_price,
                    'facevalue': facevalue,
                    'coupon_pct': (
                        coupon_pct if 'coupon_pct' in locals() else None
                    ),
                    'is_ofz': is_ofz,
                },
            )
            continue

    if errors_count > 0:
        logger.warning(f"Ошибок при расчёте: {errors_count}")

    if not results:
        logger.warning("Не удалось выполнить расчёты для найденных бумаг.")
        return

    logger.info(f"Успешно рассчитано бумаг: {len(results)}")

    res_df = pd.DataFrame(results)
    print_results(
        res_df, holding_days, buy_date, sell_date, floater_rate, scenario_key
    )


if __name__ == "__main__":
    logger.info("🚀 Запуск NetYield MOEX")

    current_cbr_rate = get_cbr_key_rate(
        fallback_rate=config.FLOATING_COUPON_RATE
    )

    print("\n" + "=" * 40)
    print(f"🏦 Ключевая ставка ЦБ РФ сегодня: {current_cbr_rate}%")
    print("=" * 40)

    buy_date, sell_date, scenario_key = get_user_scenario()

    analyze_reliable_bonds(buy_date, sell_date, scenario_key, current_cbr_rate)

    logger.info("✅ Работа завершена")
