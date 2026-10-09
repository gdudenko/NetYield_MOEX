"""
Расчёт доходности облигаций с учётом погашений, налогов и сценариев ставки.
"""

import pandas as pd

import app_config as config
from analysis.taxes import calculate_tax
from logger import get_logger

logger = get_logger(__name__)

DAYS_PER_YEAR = 365
MIN_COUPON_PCT = 1.0


def calculate_price_change(
    duration_days: float, rate_change_pct: float
) -> float:
    """
    Рассчитывает ожидаемое изменение цены облигации на основе дюрации.

    Формула: ΔЦены (%) ≈ -Дюрация (лет) × ΔСтавки (п.п.) × коэффициент

    Коэффициент учитывает выпуклость: связь цены и ставки нелинейна, при
    падении ставки цена растёт слабее, чем падает при росте. Для
    оптимистичного сценария (ставка ниже) берётся PRICE_RISE_COEF, для
    пессимистичного — PRICE_DROP_COEF.

    Пример: Дюрация = 3 года, ставка выросла на 2%
            → цена упадёт на ~6%
            Ставка упала на 2% → цена вырастет на ~4.2%, а не на 6%

    Args:
        duration_days: Дюрация в днях.
        rate_change_pct: Изменение ставки в процентных пунктах.

    Returns:
        Ожидаемое изменение цены в %.
    """
    if pd.isna(duration_days) or duration_days <= 0:
        return 0.0

    coef = (
        config.PRICE_RISE_COEF
        if rate_change_pct < 0
        else config.PRICE_DROP_COEF
    )
    duration_years = duration_days / DAYS_PER_YEAR
    return -duration_years * rate_change_pct * coef


def _finalize(
    net_profit_rub: float,
    purchase_price_rub: float,
    effective_days: int,
    status: str,
    extra: dict | None = None,
) -> dict:
    """Переводит прибыль в доходность за период и годовую.

    Оба сценария (погашение и продажа) заканчиваются одинаково: считаем
    доходность за период, пересчитываем её в годовую и собираем словарь.

    Args:
        net_profit_rub: Чистая прибыль за период в рублях.
        purchase_price_rub: Цена покупки в рублях.
        effective_days: Фактический период владения в днях.
        status: Подпись сценария для вывода.
        extra: Дополнительные поля результата.

    Returns:
        Словарь с результатами расчёта.
    """
    horizon_return_pct = (net_profit_rub / purchase_price_rub) * 100
    annualized_return = (
        (1 + horizon_return_pct / 100) ** (DAYS_PER_YEAR / effective_days) - 1
    ) * 100

    result = {
        'net_profit_rub': net_profit_rub,
        'horizon_return_pct': horizon_return_pct,
        'annualized_return': annualized_return,
        'status': status,
        'effective_days': effective_days,
    }
    if extra:
        result.update(extra)
    return result


def _coupon_income_rub(
    facevalue: float, coupon_pct: float, days: int
) -> float:
    """Сумма купонных выплат за период в рублях."""
    return facevalue * (coupon_pct / 100) * (days / DAYS_PER_YEAR)


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
    total_coupons_rub = _coupon_income_rub(
        facevalue, coupon_pct, actual_holding_days
    )
    body_profit_rub = facevalue - purchase_price_rub

    total_tax = calculate_tax(is_ofz, total_coupons_rub, body_profit_rub)

    return _finalize(
        net_profit_rub=(total_coupons_rub - total_tax) + body_profit_rub,
        purchase_price_rub=purchase_price_rub,
        effective_days=actual_holding_days,
        status='Погашение',
    )


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
    price_change_for_scenario = calculate_price_change(
        duration_days, rate_change_pct
    )

    sale_price_rub = (
        facevalue * (current_price_pct + price_change_for_scenario) / 100
    )
    body_profit_rub = sale_price_rub - purchase_price_rub

    total_coupons_rub = _coupon_income_rub(facevalue, coupon_pct, holding_days)

    total_tax = calculate_tax(is_ofz, total_coupons_rub, body_profit_rub)

    return _finalize(
        net_profit_rub=(total_coupons_rub - total_tax) + body_profit_rub,
        purchase_price_rub=purchase_price_rub,
        effective_days=holding_days,
        status='Продажа',
        extra={'price_change_pct': price_change_for_scenario},
    )


def floater_coupon_base(
    coupon_pct: float,
    coupon_estimate: float,
    floater_rate: float,
) -> float:
    """Базовая ставка купона флоатера — до сдвига на сценарий.

    Источники по убыванию надёжности:

    1. COUPONPERCENT — купон, посчитанный эмитентом на дату последнего
       расчёта. Это уже «ставка + премия», то есть ровно то, что нужно.
    2. COUPON_ESTIMATE — та же величина, восстановленная из суммы
       выплаты за купонный период. Актуально для бумаг, где биржа
       публикует сумму выплаты, но не публикует процент. Тоже учитывает
       премию эмитента.
    3. Ключевая ставка ЦБ — последний откат. Премии эмитента не знает,
       поэтому для флоатеров с премией систематически занижает купон.

    Args:
        coupon_pct: COUPONPERCENT из API (NaN, если не опубликован).
        coupon_estimate: Купон, восстановленный из COUPONVALUE.
        floater_rate: Текущая ставка ЦБ.

    Returns:
        Базовая годовая ставка купона в %.
    """
    for candidate in (coupon_pct, coupon_estimate):
        if pd.notna(candidate) and candidate >= MIN_COUPON_PCT:
            return float(candidate)
    return floater_rate


def process_coupon(
    coupon_pct: float,
    coupon_class: str,
    floater_rate: float,
    rate_change: float = 0.0,
    coupon_estimate: float = float('nan'),
) -> float | None:
    """
    Обрабатывает купон в зависимости от типа бумаги.

    Купон флоатера привязан к ставке, поэтому он двигается вместе со
    сценарием: если ставка к моменту продажи меняется на rate_change,
    купон меняется на те же п.п. Иначе в пессимистичном сценарии флоатер
    терял бы и на падении цены, и на купоне, хотя по сути его доходность
    защищена именно привязкой к ставке.

    Для остальных типов купон берётся из API без изменений.

    Args:
        coupon_pct: Купон из API (может быть NaN или 0).
        coupon_class: Класс купона ('floater', 'variable', 'fixed', 'unknown').
        floater_rate: Текущая ставка ЦБ для флоатеров.
        rate_change: Изменение ставки по сценарию, п.п.
        coupon_estimate: Купон, восстановленный из суммы купонной выплаты.

    Returns:
        Обработанный купон в % или None, если бумагу нужно пропустить.
    """
    if pd.isna(coupon_pct):
        coupon_pct = 0.0

    if coupon_class == 'floater':
        base = floater_coupon_base(
            coupon_pct, coupon_estimate, floater_rate
        )
        # Ставка не может уйти в ноль: у флоатеров есть спред к RUONIA,
        # но в сценарии -2 п.п. короткая RUONIA-премия упирается в пол.
        return max(MIN_COUPON_PCT, base + rate_change)

    # Фиксированный, переменный или неизвестный: берём купон из API.
    # Слишком маленький купон — сигнал пропустить бумагу.
    if coupon_pct < MIN_COUPON_PCT:
        return None

    return coupon_pct