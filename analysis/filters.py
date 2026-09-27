"""
Все фильтры для отбора облигаций.
"""

import pandas as pd
import config
from logger import get_logger

logger = get_logger(__name__)


def split_ofz_and_corporate(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Разделяет облигации на ОФЗ и корпоративные."""
    regex_black = '|'.join(config.BLACK_LIST_KEYWORDS)
    regex_white = '|'.join(config.WHITE_LIST_KEYWORDS)

    df_ofz = df[df['IS_OFZ']].copy()
    df_ofz = df_ofz[
        ~df_ofz['SHORTNAME'].str.contains(regex_black, case=False, na=False)
    ]

    df_corp = df[~df['IS_OFZ']].copy()
    df_corp = df_corp[
        df_corp['SHORTNAME'].str.contains(regex_white, case=False, na=False)
    ]
    df_corp = df_corp[
        ~df_corp['SHORTNAME'].str.contains(regex_black, case=False, na=False)
    ]

    logger.debug(
        f"После разделения: ОФЗ={len(df_ofz)}, Корпораты={len(df_corp)}"
    )
    return df_ofz, df_corp


def apply_bond_type_filter(df: pd.DataFrame) -> pd.DataFrame:
    """Исключает структурные, конвертируемые и валютные облигации."""
    before = len(df)
    result = df[~df['BONDTYPE'].isin(config.EXCLUDED_BOND_TYPES)]
    logger.debug(
        f"Фильтр типов облигаций: {before} → {len(result)} (-{before - len(result)})"
    )
    return result


def apply_bond_subtype_filter(df: pd.DataFrame) -> pd.DataFrame:
    """Исключает бессрочные облигации (суборды)."""
    before = len(df)
    result = df[~df['BONDSUBTYPE'].isin(config.EXCLUDED_BOND_SUBTYPES)]
    logger.debug(
        f"Фильтр подвидов (суборды): {before} → {len(result)} (-{before - len(result)})"
    )
    return result


def apply_liquidity_filter(df: pd.DataFrame) -> pd.DataFrame:
    """Фильтр по ликвидности."""
    before = len(df)
    result = df[
        (df['NUMTRADES'] >= config.MIN_NUM_TRADES)
        | (df['VALUE'] >= config.MIN_TURNOVER_RUB)
    ]
    logger.debug(
        f"Фильтр ликвидности: {before} → {len(result)} (-{before - len(result)})"
    )
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

    df_reliable = apply_bond_type_filter(df_reliable)
    df_reliable = apply_bond_subtype_filter(df_reliable)
    df_reliable = apply_liquidity_filter(df_reliable)
    df_reliable = apply_offer_filter(df_reliable, buy_ts, sell_ts)

    logger.info(f"После всех фильтров осталось бумаг: {len(df_reliable)}")
    return df_reliable
