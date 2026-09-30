"""
Классификация облигаций по типу купона на основе официальных полей Мосбиржи.
"""

import pandas as pd
import app_config as config


def classify_coupon_type(coupon_details) -> str:
    """
    Классифицирует облигацию по полю COUPON_DETAILS из API Мосбиржи.

    Args:
        coupon_details: Значение поля COUPON_DETAILS.

    Returns:
        'floater' | 'variable' | 'fixed' | 'unknown'
    """
    if pd.isna(coupon_details) or coupon_details is None:
        return 'unknown'

    coupon_details = str(coupon_details)

    if coupon_details in config.FLOATER_COUPON_TYPES:
        return 'floater'
    elif coupon_details in config.VARIABLE_COUPON_TYPES:
        return 'variable'
    elif coupon_details in config.FIXED_COUPON_TYPES:
        return 'fixed'
    else:
        return 'unknown'


def get_coupon_label(coupon_class: str) -> str:
    """Возвращает человекочитаемое название типа купона."""
    labels = {
        'floater': 'Флоатер',
        'variable': 'Переменный',
        'fixed': 'Фиксированный',
        'unknown': 'Неизвестно',
    }
    return labels.get(coupon_class, 'Неизвестно')


def apply_coupon_classification(df: pd.DataFrame) -> pd.DataFrame:
    """Добавляет колонку COUPON_CLASS в DataFrame."""
    df['COUPON_CLASS'] = df['COUPON_DETAILS'].apply(classify_coupon_type)
    return df
