"""
Получение ключевой ставки ЦБ РФ через SOAP API Банка России.
"""

import re
import xml.etree.ElementTree as ET

from error_handler import log_parse_error
from logger import get_logger
from services.http import request_with_logging

logger = get_logger(__name__)

CBR_URL = 'http://www.cbr.ru/DailyInfoWebServ/DailyInfo.asmx'
DATA_SOURCE = 'ЦБ РФ SOAP API'

SOAP_BODY = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               xmlns:xsd="http://www.w3.org/2001/XMLSchema"
               xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <MainInfoXML xmlns="http://web.cbr.ru/" />
  </soap:Body>
</soap:Envelope>"""

HEADERS = {
    'Content-Type': 'text/xml; charset=utf-8',
    'SOAPAction': 'http://web.cbr.ru/MainInfoXML',
}

KEY_RATE_PATTERNS = (
    r'<[^:]*:?keyRate[^>]*>\s*(\d{1,2}[.,]\d{2})\s*<',
    r'<[^:]*:?KeyRate[^>]*>\s*(\d{1,2}[.,]\d{2})\s*<',
)


def _use_fallback(fallback_rate: float) -> float:
    """Резервная ставка с предупреждением в лог."""
    logger.warning(f"Использую резервное значение: {fallback_rate}%")
    return fallback_rate


def _parse_with_elementtree(raw: bytes, content: str) -> float | None:
    """Стратегия 1: разбор XML стандартной библиотекой."""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        log_parse_error(
            e,
            data_source=DATA_SOURCE,
            data_preview=content[:500],
            context="Парсинг XML ответа от ЦБ РФ",
        )
        return None

    for elem in root.iter():
        if elem.tag.split('}')[-1].lower() != 'keyrate' or not elem.text:
            continue

        rate_date = elem.get('Date', 'неизвестно')
        try:
            key_rate = float(elem.text.strip().replace(',', '.'))
        except (ValueError, TypeError) as e:
            log_parse_error(
                e,
                data_source=DATA_SOURCE,
                data_preview=content[:300],
                context="Преобразование ставки из текста в число",
            )
            continue

        logger.info(f"✅ Ключевая ставка ЦБ РФ: {key_rate}% (от {rate_date})")
        return key_rate

    return None


def _parse_with_regex(content: str) -> float | None:
    """Стратегия 2: регулярные выражения, если XML не разобрался."""
    for i, pattern in enumerate(KEY_RATE_PATTERNS, 1):
        match = re.search(pattern, content, re.IGNORECASE)
        if not match:
            continue

        try:
            key_rate = float(match.group(1).replace(',', '.'))
        except ValueError as e:
            log_parse_error(
                e,
                data_source=DATA_SOURCE,
                data_preview=match.group(0),
                context=f"Преобразование ставки из regex паттерна {i}",
            )
            continue

        logger.info(f"✅ Ключевая ставка ЦБ РФ (regex): {key_rate}%")
        return key_rate

    return None


def get_cbr_key_rate(fallback_rate: float = 16.0) -> float:
    """Получает актуальную ключевую ставку ЦБ РФ через SOAP API.

    Args:
        fallback_rate: Ставка, если сервис недоступен или ответ не разобран.

    Returns:
        Ключевая ставка в процентах.
    """
    logger.info("Запрашиваю ключевую ставку ЦБ РФ через SOAP API...")

    response = request_with_logging(
        'POST',
        CBR_URL,
        context="Запрос ключевой ставки ЦБ РФ",
        data=SOAP_BODY,
        headers=HEADERS,
        timeout=15,
    )
    if response is None:
        return _use_fallback(fallback_rate)

    content = response.content.decode('utf-8', errors='replace')

    key_rate = _parse_with_elementtree(response.content, content)
    if key_rate is None:
        key_rate = _parse_with_regex(content)

    if key_rate is None:
        logger.warning("Не удалось найти ключевую ставку в ответе ЦБ.")
        return _use_fallback(fallback_rate)

    return key_rate