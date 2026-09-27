"""
Расчёт налогов для ОФЗ и корпоративных облигаций.
"""

import config


def calculate_tax(
    is_ofz: bool, coupons_rub: float, body_profit_rub: float
) -> float:
    """
    Рассчитывает налог на доход от облигации.

    Для ОФЗ: налог только на купоны (льгота на дисконт при погашении).
    Для корпоративных: сальдирование купонов и прибыли/убытка с тела.

    Args:
        is_ofz: Является ли бумага ОФЗ.
        coupons_rub: Сумма купонов в рублях.
        body_profit_rub: Прибыль/убыток от тела облигации.

    Returns:
        Сумма налога в рублях.
    """
    if is_ofz:
        # ОФЗ: налог только на купоны
        return coupons_rub * config.TAX_RATE
    else:
        # Корпораты: сальдируем купоны и прибыль/убыток с тела
        tax_base = coupons_rub + body_profit_rub
        if tax_base > 0:
            return tax_base * config.TAX_RATE
        return 0.0
