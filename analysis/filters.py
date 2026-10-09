"""
Все фильтры для отбора облигаций.
"""

# pandas-стабы считают df[маска] типом "Series | DataFrame", поэтому любой
# фильтр с булевой маской даёт ложную ошибку возврата. Точные типы здесь не
# нужны — на вход и на выход DataFrame, это проверяется рантаймом.
# pyright: reportReturnType=false

import pandas as pd

import app_config as config
from logger import get_logger

logger = get_logger(__name__)


def _log_filter(name: str, before: int, after: int) -> None:
    """Логирует, сколько бумаг отсеял фильтр."""
    logger.debug(f"Фильтр {name}: {before} → {after} (-{before - after})")


def _is_name_allowed(names, *regexes: str) -> pd.Series:
    """Совпадение хотя бы по одному регулярному выражению."""
    combined = '|'.join(regexes)
    return names.str.contains(combined, case=False, na=False)


def split_ofz_and_corporate(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Разделяет облигации на ОФЗ и корпоративные.

    Чёрный список (суборды, конвертируемые и т.п.) отсекается с обеих
    сторон: у корпоративных он дополняет белый список.
    """
    df_ofz = df[df['IS_OFZ']].copy()
    df_ofz = df_ofz[
        ~_is_name_allowed(df_ofz['SHORTNAME'], *config.BLACK_LIST_KEYWORDS)
    ]

    df_corp = df[~df['IS_OFZ']].copy()
    df_corp = df_corp[
        _is_name_allowed(df_corp['SHORTNAME'], *config.WHITE_LIST_KEYWORDS)
    ]
    df_corp = df_corp[
        ~_is_name_allowed(df_corp['SHORTNAME'], *config.BLACK_LIST_KEYWORDS)
    ]

    logger.debug(
        f"После разделения: ОФЗ={len(df_ofz)}, Корпораты={len(df_corp)}"
    )
    return df_ofz, df_corp


def apply_bond_type_filter(df: pd.DataFrame) -> pd.DataFrame:
    """Исключает структурные, конвертируемые и валютные облигации."""
    before = len(df)
    result = df[~df['BONDTYPE'].isin(config.EXCLUDED_BOND_TYPES)]
    _log_filter('типов облигаций', before, len(result))
    return result


def apply_bond_subtype_filter(df: pd.DataFrame) -> pd.DataFrame:
    """Исключает бессрочные облигации (суборды)."""
    before = len(df)
    result = df[~df['BONDSUBTYPE'].isin(config.EXCLUDED_BOND_SUBTYPES)]
    _log_filter('подвидов (суборды)', before, len(result))
    return result


def apply_liquidity_filter(df: pd.DataFrame) -> pd.DataFrame:
    """Фильтр по ликвидности: сделки либо оборот."""
    before = len(df)
    result = df[
        (df['NUMTRADES'] >= config.MIN_NUM_TRADES)
        | (df['VALUE'] >= config.MIN_TURNOVER_RUB)
    ]
    _log_filter('ликвидности', before, len(result))
    return result


def apply_offer_filter(
    df: pd.DataFrame, buy_ts: pd.Timestamp, sell_ts: pd.Timestamp
) -> pd.DataFrame:
    """Исключает бумаги, у которых оферта попадает внутрь периода владения."""
    before = len(df)

    mask_offer_risk = (
        df['OFFERDATE'].notna()
        & (df['OFFERDATE'] >= buy_ts)
        & (df['OFFERDATE'] <= sell_ts)
    )
    result = df[~mask_offer_risk]

    excluded_count = before - len(result)
    if excluded_count > 0:
        logger.info(
            f"🛡️ Исключено бумаг с офертой в периоде: {excluded_count}"
        )

    return result


def apply_all_filters(
    df: pd.DataFrame, buy_ts: pd.Timestamp, sell_ts: pd.Timestamp
) -> pd.DataFrame:
    """Применяет все фильтры последовательно."""
    logger.info("Применяю фильтры отбора облигаций...")

    df_ofz, df_corp = split_ofz_and_corporate(df)
    df_reliable = pd.concat([df_ofz, df_corp])

    for step in (
        apply_bond_type_filter,
        apply_bond_subtype_filter,
        apply_liquidity_filter,
    ):
        df_reliable = step(df_reliable)
    df_reliable = apply_offer_filter(df_reliable, buy_ts, sell_ts)

    logger.info(f"После всех фильтров осталось бумаг: {len(df_reliable)}")
    return df_reliable