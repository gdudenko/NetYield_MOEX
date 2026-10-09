"""
Получение данных по облигациям с Московской биржи (MOEX ISS API).
"""

# pandas-стабы не знают, что df['COLUMN'] — это Series, и ругаются на
# любой вызов метода у результата индексации. Данные приходят из API с
# заранее известной структурой, типы здесь не проверяются.
# pyright: reportAttributeAccessIssue=false, reportReturnType=false
# pyright: reportAssignmentType=false

import pandas as pd

import app_config as config
from error_handler import log_parse_error
from logger import get_logger
from services.http import request_with_logging

logger = get_logger(__name__)

DATA_SOURCE = 'MOEX ISS API'

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