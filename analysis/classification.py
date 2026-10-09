"""
Классификация облигаций по типу купона на основе официальных полей Мосбиржи.
"""

import pandas as pd

import app_config as config

UNKNOWN = 'unknown'

# Значения COUPON_DETAILS → класс купона. Строится из настроек один раз,
# чтобы новый тип в app_config не требал правок здесь.
COUPON_CLASS_BY_DETAIL: dict[str, str] = {
    **{detail: 'floater' for detail in config.FLOATER_COUPON_TYPES},
    **{detail: 'variable' for detail in config.VARIABLE_COUPON_TYPES},
    **{detail: 'fixed' for detail in config.FIXED_COUPON_TYPES},
}

COUPON_LABELS = {
    'floater': 'Флоатер',
    'variable': 'Переменный',
    'fixed': 'Фиксированный',
    UNKNOWN: 'Неизвестно',
}


def classify_coupon_type(coupon_details) -> str:
    """
    Классифицирует облигацию по полю COUPON_DETAILS из API Мосбиржи.

    Args:
        coupon_details: Значение поля COUPON_DETAILS.

    Returns:
        'floater' | 'variable' | 'fixed' | 'unknown'
    """
    if pd.isna(coupon_details) or coupon_details is None:
        return UNKNOWN

    return COUPON_CLASS_BY_DETAIL.get(str(coupon_details), UNKNOWN)


def get_coupon_label(coupon_class: str) -> str:
    """Возвращает человекочитаемое название типа купона."""
    return COUPON_LABELS.get(coupon_class, COUPON_LABELS[UNKNOWN])


def apply_coupon_classification(df: pd.DataFrame) -> pd.DataFrame:
    """Добавляет колонку COUPON_CLASS в DataFrame."""
    df['COUPON_CLASS'] = df['COUPON_DETAILS'].apply(classify_coupon_type)
    return df