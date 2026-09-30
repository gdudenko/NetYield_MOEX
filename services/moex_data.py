"""
Получение данных по облигациям с Московской биржи (MOEX ISS API).
"""

import requests
import pandas as pd
import app_config as config
from logger import get_logger
from error_handler import log_network_error, log_parse_error

logger = get_logger(__name__)


def fetch_moex_data() -> pd.DataFrame | None:
    """Запрашивает данные по облигациям с Московской биржи."""
    logger.info("Запрашиваю данные с Московской биржи...")

    try:
        response = requests.get(
            config.MOEX_API_URL, params=config.API_PARAMS, timeout=30
        )
        response.raise_for_status()

        try:
            data = response.json()
        except ValueError as e:
            log_parse_error(
                e,
                data_source="MOEX ISS API",
                data_preview=response.text[:500],
                context="Парсинг JSON ответа от Мосбиржи",
            )
            return None

        logger.debug(
            f"Получен ответ от Мосбиржи, статус: {response.status_code}"
        )

        try:
            df_sec = pd.DataFrame(
                data['securities']['data'],
                columns=data['securities']['columns'],
            )
            df_market = pd.DataFrame(
                data['marketdata']['data'],
                columns=data['marketdata']['columns'],
            )

            df_yields = pd.DataFrame(
                data.get('marketdata_yields', {}).get('data', []),
                columns=data.get('marketdata_yields', {}).get('columns', []),
            )
        except (KeyError, TypeError) as e:
            log_parse_error(
                e,
                data_source="MOEX ISS API",
                data_preview=str(data)[:500],
                context="Извлечение данных из JSON ответа",
            )
            return None

        duplicates_market = df_market.duplicated(subset=['SECID']).sum()
        if duplicates_market > 0:
            logger.debug(
                f"Удалено дубликатов в marketdata: {duplicates_market}"
            )

        df_market = df_market.drop_duplicates(subset=['SECID'], keep='first')

        if not df_yields.empty:
            df_yields = df_yields.drop_duplicates(
                subset=['SECID'], keep='first'
            )

        df = pd.merge(df_sec, df_market, on='SECID', how='inner')

        if not df_yields.empty:
            df_yields = df_yields.rename(
                columns={
                    'DURATION': 'DURATION_YIELDS',
                    'EFFECTIVEYIELD': 'EFFECTIVE_YIELD',
                }
            )
            df = pd.merge(df, df_yields, on='SECID', how='left')

        logger.info(f"Загружено облигаций: {len(df)}")
        return df

    except requests.exceptions.RequestException as e:
        log_network_error(
            e,
            url=config.MOEX_API_URL,
            context="Запрос данных с Московской биржи",
            response_status=(
                getattr(e.response, 'status_code', None)
                if hasattr(e, 'response')
                else None
            ),
            response_content=(
                getattr(e.response, 'text', None)
                if hasattr(e, 'response')
                else None
            ),
        )
        return None

    except Exception as e:
        from error_handler import log_error

        log_error(
            e,
            context="Неожиданная ошибка при загрузке данных с Мосбиржи",
            include_stack=True,
        )
        return None


def prepare_data(df: pd.DataFrame) -> pd.DataFrame:
    """Подготавливает данные: очищает, приводит типы, добавляет производные поля."""
    initial_count = len(df)

    df['PRICE_PCT'] = df['LAST'].fillna(df['LCLOSEPRICE'])
    df = df[df['PRICE_PCT'].notna()]

    dropped = initial_count - len(df)
    if dropped > 0:
        logger.debug(f"Отсеяно бумаг без цены: {dropped}")

    df['NUMTRADES'] = pd.to_numeric(df['NUMTRADES'], errors='coerce').fillna(0)
    df['VALUE'] = pd.to_numeric(df['VALUE'], errors='coerce').fillna(0)

    df['OFFERDATE'] = pd.to_datetime(df['OFFERDATE'], errors='coerce')
    df['MATDATE'] = pd.to_datetime(df['MATDATE'], errors='coerce')

    if 'DURATION_YIELDS' in df.columns:
        df['DURATION_DAYS'] = df['DURATION_YIELDS'].fillna(df['DURATION'])
    else:
        df['DURATION_DAYS'] = df['DURATION']

    df['DURATION_DAYS'] = pd.to_numeric(
        df['DURATION_DAYS'], errors='coerce'
    ).fillna(0)

    df['IS_OFZ'] = df['BONDTYPE'].str.contains('OFZ', na=False) | df[
        'SECID'
    ].str.startswith('SU')

    ofz_count = df['IS_OFZ'].sum()
    corp_count = len(df) - ofz_count
    logger.debug(
        f"Подготовка завершена: ОФЗ={ofz_count}, Корпоративные={corp_count}"
    )

    return df
