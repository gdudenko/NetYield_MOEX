"""
Расчёт доходности облигаций с учётом погашений, налогов и сценариев ставки.
"""

import pandas as pd
import config
from analysis.taxes import calculate_tax
from logger import get_logger

logger = get_logger(__name__)


def calculate_price_change(
    duration_days: float, rate_change_pct: float
) -> float:
    """
    Рассчитывает ожидаемое изменение цены облигации на основе дюрации.

    Формула: ΔЦены (%) ≈ -Дюрация (лет) × ΔСтавки (%)

    Пример: Дюрация = 3 года, ставка выросла на 2%
            → цена упадёт на ~6%

    Args:
        duration_days: Дюрация в днях.
        rate_change_pct: Изменение ставки в процентных пунктах.

    Returns:
        Ожидаемое изменение цены в %.
    """
    if pd.isna(duration_days) or duration_days <= 0:
        return 0.0

    duration_years = duration_days / 365.0
    return -duration_years * rate_change_pct


def calculate_maturity_scenario(
    facevalue: float,
    purchase_price_rub: float,
    coupon_pct: float,
    actual_holding_days: int,
    is_ofz: bool,
) -> dict:
    """
    Расчёт доходности при погашении облигации внутри периода владения.

    При погашении эмитент возвращает номинал, изменение цены не применяется.

    Args:
        facevalue: Номинал облигации.
        purchase_price_rub: Цена покупки в рублях.
        coupon_pct: Ставка купона в %.
        actual_holding_days: Фактический период владения в днях.
        is_ofz: Является ли бумага ОФЗ.

    Returns:
        Словарь с результатами расчёта.
    """
    total_coupons_rub = (
        facevalue * (coupon_pct / 100) * (actual_holding_days / 365)
    )
    redemption_rub = facevalue
    body_profit_rub = redemption_rub - purchase_price_rub

    total_tax = calculate_tax(is_ofz, total_coupons_rub, body_profit_rub)

    net_profit_rub = (
        (total_coupons_rub - total_tax) + redemption_rub - purchase_price_rub
    )

    horizon_return_pct = (net_profit_rub / purchase_price_rub) * 100
    annualized_return = (
        (1 + horizon_return_pct / 100) ** (365 / actual_holding_days) - 1
    ) * 100

    return {
        'net_profit_rub': net_profit_rub,
        'horizon_return_pct': horizon_return_pct,
        'annualized_return': annualized_return,
        'status': 'Погашение',
        'effective_days': actual_holding_days,
    }


def calculate_sale_scenario(
    facevalue: float,
    purchase_price_rub: float,
    current_price_pct: float,
    coupon_pct: float,
    holding_days: int,
    is_ofz: bool,
    duration_days: float,
    rate_change_pct: float,
) -> dict:
    """
    Расчёт доходности при продаже облигации на бирже.

    Цена продажи рассчитывается с учётом изменения ставки (через дюрацию).

    Args:
        facevalue: Номинал облигации.
        purchase_price_rub: Цена покупки в рублях.
        current_price_pct: Текущая цена в % от номинала.
        coupon_pct: Ставка купона в %.
        holding_days: Период владения в днях.
        is_ofz: Является ли бумага ОФЗ.
        duration_days: Дюрация в днях.
        rate_change_pct: Изменение ставки в п.п. (по сценарию).

    Returns:
        Словарь с результатами расчёта.
    """
    # Рассчитываем изменение цены по дюрации
    price_change_for_scenario = calculate_price_change(
        duration_days, rate_change_pct
    )

    sale_price_rub = (
        facevalue * (current_price_pct + price_change_for_scenario) / 100
    )
    body_profit_rub = sale_price_rub - purchase_price_rub

    total_coupons_rub = facevalue * (coupon_pct / 100) * (holding_days / 365)

    total_tax = calculate_tax(is_ofz, total_coupons_rub, body_profit_rub)

    net_profit_rub = (total_coupons_rub - total_tax) + body_profit_rub

    horizon_return_pct = (net_profit_rub / purchase_price_rub) * 100
    annualized_return = (
        (1 + horizon_return_pct / 100) ** (365 / holding_days) - 1
    ) * 100

    return {
        'net_profit_rub': net_profit_rub,
        'horizon_return_pct': horizon_return_pct,
        'annualized_return': annualized_return,
        'price_change_pct': price_change_for_scenario,
        'status': 'Продажа',
        'effective_days': holding_days,
    }


def process_coupon(
    coupon_pct: float, coupon_class: str, floater_rate: float
) -> float | None:
    """
    Обрабатывает купон в зависимости от типа бумаги.

    Для флоатеров с неизвестным купоном подставляет ставку ЦБ.
    Для остальных типов использует купон из API.

    Args:
        coupon_pct: Купон из API (может быть NaN или 0).
        coupon_class: Класс купона ('floater', 'variable', 'fixed', 'unknown').
        floater_rate: Текущая ставка ЦБ для флоатеров.

    Returns:
        Обработанный купон в % или None, если бумагу нужно пропустить.
    """
    if pd.isna(coupon_pct):
        coupon_pct = 0.0

    if coupon_class == 'floater':
        # Флоатер: купон неизвестен, используем ставку ЦБ как прогноз
        if coupon_pct < 1.0:
            return floater_rate
        return coupon_pct
    else:
        # Фиксированный, переменный или неизвестный: используем купон из API
        if coupon_pct < 1.0:
            return None  # Сигнал пропустить бумагу
        return coupon_pct
