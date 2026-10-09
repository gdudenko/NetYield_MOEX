"""
Получение данных по облигациям с Московской биржи (MOEX ISS API).
"""

# pandas-стабы не знают, что df['COLUMN'] — это Series, и ругаются на
# любой вызов метода у результата индексации. Данные приходят из API с
# заранее известной структурой, типы здесь не проверяются.
# pyright: reportAttributeAccessIssue=false, reportReturnType=false
# pyright: reportAssignmentType=false

import numpy as np
import pandas as pd

import app_config as config
from error_handler import log_parse_error
from logger import get_logger
from services.http import request_with_logging

logger = get_logger(__name__)

DATA_SOURCE = 'MOEX ISS API'
DAYS_PER_YEAR = 365

SECTIONS = ('securities', 'marketdata')
YIELDS_SECTION = 'marketdata_yields'


def _sections_to_frames(data: dict) -> tuple[pd.DataFrame, ...]:
    """Собирает DataFrame из секций ответа ISS.

    Raises:
        KeyError, TypeError: Секции или их формат не совпали с ожиданием.
    """
    return tuple(
        pd.DataFrame(data[name]['data'], columns=data[name]['columns'])
        for name in SECTIONS
    )


def _fetch_sections(response_data: dict) -> tuple[pd.DataFrame, ...]:
    """Секции securities и marketdata с проверкой формата."""
    try:
        return _sections_to_frames(response_data)
    except (KeyError, TypeError) as e:
        log_parse_error(
            e,
            data_source=DATA_SOURCE,
            data_preview=str(response_data)[:500],
            context="Извлечение данных из JSON ответа",
        )
        raise


def _fetch_yields(response_data: dict) -> pd.DataFrame:
    """Секция доходностей marketdata_yields, если сервер её прислал."""
    block = response_data.get(YIELDS_SECTION) or {}
    return pd.DataFrame(block.get('data', []), columns=block.get('columns', []))


def _merge_sections(
    df_sec: pd.DataFrame,
    df_market: pd.DataFrame,
    df_yields: pd.DataFrame,
) -> pd.DataFrame:
    """Склеивает секции по SECID, убирая дубликаты рыночных данных."""
    duplicates_market = df_market.duplicated(subset=['SECID']).sum()
    if duplicates_market > 0:
        logger.debug(f"Удалено дубликатов в marketdata: {duplicates_market}")

    df_market = df_market.drop_duplicates(subset=['SECID'], keep='first')
    df = pd.merge(df_sec, df_market, on='SECID', how='inner')

    if not df_yields.empty:
        df_yields = df_yields.drop_duplicates(subset=['SECID'], keep='first')
        df_yields = df_yields.rename(
            columns={
                'DURATION': 'DURATION_YIELDS',
                'EFFECTIVEYIELD': 'EFFECTIVE_YIELD',
            }
        )
        df = pd.merge(df, df_yields, on='SECID', how='left')

    return df


def fetch_moex_data() -> pd.DataFrame | None:
    """Запрашивает данные по облигациям с Московской биржи.

    Returns:
        DataFrame с сырыми полями ISS API или None при любой ошибке.
    """
    logger.info("Запрашиваю данные с Московской биржи...")

    response = request_with_logging(
        'GET',
        config.MOEX_API_URL,
        context="Запрос данных с Московской биржи",
        params=config.API_PARAMS,
        timeout=30,
    )
    if response is None:
        return None

    try:
        data = response.json()
    except ValueError as e:
        log_parse_error(
            e,
            data_source=DATA_SOURCE,
            data_preview=response.text[:500],
            context="Парсинг JSON ответа от Мосбиржи",
        )
        return None

    try:
        df_sec, df_market = _fetch_sections(data)
        df_yields = _fetch_yields(data)
        df = _merge_sections(df_sec, df_market, df_yields)
    except (KeyError, TypeError):
        return None

    logger.info(f"Загружено облигаций: {len(df)}")
    return df


def _coupon_from_value(df: pd.DataFrame) -> pd.Series:
    """Годовая ставка купона в % из COUPONVALUE и COUPONPERIOD.

    COUPONVALUE — сумма выплаты на один купонный период в рублях.
    Годовая ставка = COUPONVALUE / FACEVALUE × 365 / COUPONPERIOD × 100.

    Где выплаты ещё не рассчитаны (COUPONVALUE = 0), возвращается NaN —
    там пойдёт откат на ключевую ставку.

    Если биржа не отдала COUPONVALUE вовсе, тоже NaN: расчёт продолжает
    работать на ставке ЦБ, лучше потерять премию, чем упасть.
    """
    needed = ('COUPONVALUE', 'COUPONPERIOD', 'FACEVALUE')
    if not all(column in df.columns for column in needed):
        logger.warning(
            'Нет полей %s — купон флоатера берётся только из ставки ЦБ',
            ', '.join(column for column in needed if column not in df.columns),
        )
        return pd.Series(np.nan, index=df.index)

    cols = df[list(needed)].apply(pd.to_numeric, errors='coerce')
    value = cols['COUPONVALUE']
    period = cols['COUPONPERIOD']

    estimate = value / cols['FACEVALUE'] * DAYS_PER_YEAR / period * 100
    return estimate.where((value > 0) & (period > 0))


def prepare_data(df: pd.DataFrame) -> pd.DataFrame:
    """Готовит данные: чистит, приводит типы, добавляет производные поля."""
    initial_count = len(df)

    df['PRICE_PCT'] = df['LAST'].fillna(df['LCLOSEPRICE'])
    df = df[df['PRICE_PCT'].notna()]

    dropped = initial_count - len(df)
    if dropped > 0:
        logger.debug(f"Отсеяно бумаг без цены: {dropped}")

    for column in ('NUMTRADES', 'VALUE'):
        df[column] = pd.to_numeric(df[column], errors='coerce').fillna(0)

    # Купон флоатера, посчитанный эмитентом по ставке: сумма выплаты за
    # купонный период, приведённая к годовой ставке в %. Для бумаг, у которых
    # биржа не публикует COUPONPERCENT, это единственный источник купона
    # кроме ставки ЦБ — и он учитывает премию эмитента (RUONIA/КС + спред).
    df['COUPON_ESTIMATE'] = _coupon_from_value(df)

    for column in ('OFFERDATE', 'MATDATE'):
        df[column] = pd.to_datetime(df[column], errors='coerce')

    # Дюрация приходит и в marketdata, и в marketdata_yields; поля называются
    # по-разному, приоритет у блока доходностей.
    source = df['DURATION']
    if 'DURATION_YIELDS' in df.columns:
        source = df['DURATION_YIELDS'].fillna(source)
    df['DURATION_DAYS'] = pd.to_numeric(source, errors='coerce').fillna(0)

    df['IS_OFZ'] = df['BONDTYPE'].str.contains('OFZ', na=False) | df[
        'SECID'
    ].str.startswith('SU')

    logger.debug(
        f"Подготовка завершена: ОФЗ={df['IS_OFZ'].sum()}, "
        f"Корпоративные={len(df) - df['IS_OFZ'].sum()}"
    )

    return df