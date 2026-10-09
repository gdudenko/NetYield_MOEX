"""
Ядро анализа: полный цикл от данных Мосбиржи до готового DataFrame.

Оба интерфейса (консольный и GUI) вызывают run_analysis() и отличаются
только способом показать результат. Логика расчёта, фильтрации и
обработки ошибок живёт здесь в единственном экземпляре.
"""

from typing import cast

import pandas as pd

import app_config as config
from analysis.classification import (
    apply_coupon_classification,
    get_coupon_label,
)
from analysis.filters import apply_all_filters
from analysis.result_schema import build_row
from analysis.yield_calculator import (
    calculate_maturity_scenario,
    calculate_sale_scenario,
    process_coupon,
)
from error_handler import log_calculation_error
from logger import get_logger
from services.moex_data import fetch_moex_data, prepare_data

logger = get_logger(__name__)

DATE_FORMAT = '%d.%m.%Y'
NO_DATE = 'Нет'


class AnalysisError(Exception):
    """Ошибка, которую нужно показать пользователю как есть."""


def _timestamp(value) -> pd.Timestamp:
    """Дата в виде Timestamp для сравнения с датами из API.

    cast здесь формальный: на вход всегда date из календаря или из
    консоли, NaT невозможен — но стабы pandas это не различают.
    """
    return cast(pd.Timestamp, pd.Timestamp(value))


def _safe_secid(bond: dict) -> str:
    """Достаёт SECID строкой, даже если поле отсутствует или не строка."""
    raw_secid = bond.get('SECID', 'unknown')
    return raw_secid if isinstance(raw_secid, str) else 'unknown'


def _format_date(value) -> str:
    """Дата в формате ДД.ММ.ГГГГ или 'Нет', если её нет."""
    if pd.isna(value):
        return NO_DATE
    return value.strftime(DATE_FORMAT)


def _calculate_bond(
    bond: dict,
    buy_date,
    buy_ts: pd.Timestamp,
    sell_ts: pd.Timestamp,
    holding_days: int,
    rate_change: float,
    floater_rate: float,
) -> dict | None:
    """Считает доходность по одной бумаге.

    Args:
        bond: Строка DataFrame, уже переведённая в словарь (to_dict).
        buy_date: Дата покупки, нужна для расчёта дней до погашения.

    Returns:
        Словарь с полями результата по схеме result_schema
        или None, если бумагу нужно пропустить.
    """
    secid = _safe_secid(bond)

    facevalue = bond['FACEVALUE']
    current_price = bond['PRICE_PCT']
    is_ofz = bond['IS_OFZ']
    mat_date = bond['MATDATE']
    coupon_class = bond['COUPON_CLASS']
    duration_days = bond['DURATION_DAYS']

    if pd.isna(current_price) or pd.isna(facevalue) or current_price <= 0:
        logger.debug(f"{secid}: пропущена (некорректная цена или номинал)")
        return None

    # Купон из выплаты нужен только флоатерам: у остальных типов он
    # всегда есть в API, а если нет — бумага отсеивается.
    coupon_estimate = bond.get('COUPON_ESTIMATE')
    coupon_pct = process_coupon(
        bond['COUPONPERCENT'],
        coupon_class,
        floater_rate,
        rate_change,
        coupon_estimate=(
            coupon_estimate if coupon_estimate is not None else float('nan')
        ),
    )
    if coupon_pct is None:
        logger.debug(f"{secid}: пропущена (купон < 1% и не флоатер)")
        return None

    purchase_price_rub = facevalue * current_price / 100

    if _matures_within_period(bond, buy_ts, sell_ts):
        actual_holding_days = (mat_date.date() - buy_date).days
        if actual_holding_days <= 0:
            return None

        calc = calculate_maturity_scenario(
            facevalue=facevalue,
            purchase_price_rub=purchase_price_rub,
            coupon_pct=coupon_pct,
            actual_holding_days=actual_holding_days,
            is_ofz=is_ofz,
        )
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

    return {
        'Тикер': secid,
        'Тип': 'ОФЗ' if is_ofz else 'Корпорат',
        'Эмитент': bond['SHORTNAME'],
        'Тип купона': get_coupon_label(coupon_class),
        'Цена (%)': current_price,
        'Купон (%)': coupon_pct,
        'Погашение': _format_date(mat_date),
        'Оферта': _format_date(bond['OFFERDATE']),
        'Статус': calc['status'],
        'Дней': calc['effective_days'],
        'Сделок': bond['NUMTRADES'],
        'Оборот (тыс)': bond['VALUE'] / 1000,
        'Чист. доход (₽)': calc['net_profit_rub'],
        'Доход. за период (%)': calc['horizon_return_pct'],
        'Годовая доход. (%)': calc['annualized_return'],
    }


def _load_bonds(buy_date, sell_date) -> pd.DataFrame:
    """Загружает, готовит, классифицирует и фильтрует облигации.

    Raises:
        AnalysisError: Данные не получены или после фильтров пусто.
    """
    df = fetch_moex_data()
    if df is None or df.empty:
        raise AnalysisError("Не удалось получить данные для анализа")

    df = prepare_data(df)
    df = apply_coupon_classification(df)

    df = apply_all_filters(
        df, _timestamp(buy_date), _timestamp(sell_date)
    )

    if df.empty:
        raise AnalysisError("По заданным фильтрам бумаги не найдены")

    return df


def run_analysis(
    buy_date, sell_date, scenario_key: str, floater_rate: float
) -> pd.DataFrame:
    """Выполняет полный цикл анализа.

    Args:
        buy_date: Дата покупки.
        sell_date: Дата продажи.
        scenario_key: Ключ сценария из config.RATE_SCENARIOS.
        floater_rate: Текущая ключевая ставка ЦБ (для флоатеров).

    Returns:
        DataFrame по схеме analysis.result_schema.

    Raises:
        AnalysisError: Данные не получены или после фильтров пусто.
    """
    scenario = config.get_scenario(scenario_key)

    logger.info("=" * 60)
    logger.info("Запуск анализа облигаций")
    logger.info(f"Период: {buy_date} → {sell_date}")
    logger.info(f"Сценарий: {scenario['name']}")
    logger.info("=" * 60)

    df = _load_bonds(buy_date, sell_date)

    holding_days = (sell_date - buy_date).days
    rate_change = scenario['rate_change']
    buy_ts = _timestamp(buy_date)
    sell_ts = _timestamp(sell_date)

    logger.info("Рассчитываю доходность для каждой бумаги...")
    results = []
    errors_count = 0

    for _, row in df.iterrows():
        # Строку сразу переводим в словарь: дальше идут точечные обращения
        # к полям, а не повторный поиск по Series.
        bond = row.to_dict()
        # Инициализируем до try: обработчику ошибок это нужно, даже если
        # расчёт упал на самом первом шаге.
        matures = False

        try:
            matures = _matures_within_period(bond, buy_ts, sell_ts)
            raw = _calculate_bond(
                bond,
                buy_date,
                buy_ts,
                sell_ts,
                holding_days,
                rate_change,
                floater_rate,
            )
            if raw is None:
                continue
            results.append(build_row(raw))

        except Exception as e:
            errors_count += 1
            log_calculation_error(
                e,
                bond_id=_safe_secid(bond),
                calculation_type='maturity' if matures else 'sale',
                input_data={
                    'current_price': bond.get('PRICE_PCT'),
                    'facevalue': bond.get('FACEVALUE'),
                    'coupon_pct': bond.get('COUPONPERCENT'),
                    'is_ofz': bond.get('IS_OFZ'),
                },
            )
            continue

    if errors_count > 0:
        logger.warning(f"Ошибок при расчёте: {errors_count}")

    if not results:
        raise AnalysisError(
            "Не удалось выполнить расчёты для найденных бумаг"
        )

    logger.info(f"Успешно рассчитано бумаг: {len(results)}")
    return pd.DataFrame(results)


def _matures_within_period(
    bond: dict, buy_ts: pd.Timestamp, sell_ts: pd.Timestamp
) -> bool:
    """Погашается ли бумага внутри периода владения.

    Нужно обработчику ошибок, чтобы понять, на каком расчёте упало.
    """
    mat_date = bond.get('MATDATE')
    if mat_date is None or pd.isna(mat_date):
        return False
    return bool(mat_date <= sell_ts and mat_date > buy_ts)