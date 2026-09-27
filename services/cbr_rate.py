"""
Получение ключевой ставки ЦБ РФ через SOAP API Банка России.
"""

import re
import requests
import xml.etree.ElementTree as ET
from logger import get_logger
from error_handler import log_network_error, log_parse_error

logger = get_logger(__name__)


def get_cbr_key_rate(fallback_rate: float = 16.0) -> float:
    """Получает актуальную ключевую ставку ЦБ РФ через SOAP API."""
    url = "http://www.cbr.ru/DailyInfoWebServ/DailyInfo.asmx"

    soap_body = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" 
               xmlns:xsd="http://www.w3.org/2001/XMLSchema" 
               xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <MainInfoXML xmlns="http://web.cbr.ru/" />
  </soap:Body>
</soap:Envelope>"""

    headers = {
        'Content-Type': 'text/xml; charset=utf-8',
        'SOAPAction': 'http://web.cbr.ru/MainInfoXML',
    }

    try:
        logger.info("Запрашиваю ключевую ставку ЦБ РФ через SOAP API...")
        response = requests.post(
            url, data=soap_body, headers=headers, timeout=15
        )
        response.raise_for_status()

        content = response.content.decode('utf-8', errors='replace')
        logger.debug(f"Получен ответ от ЦБ РФ, статус: {response.status_code}")

        # Стратегия 1: ElementTree
        try:
            root = ET.fromstring(response.content)

            for elem in root.iter():
                local_name = elem.tag.split('}')[-1].lower()

                if local_name == 'keyrate' and elem.text:
                    try:
                        rate_str = elem.text.strip().replace(',', '.')
                        key_rate = float(rate_str)
                        rate_date = elem.get('Date', 'неизвестно')
                        logger.info(
                            f"✅ Ключевая ставка ЦБ РФ: {key_rate}% (от {rate_date})"
                        )
                        return key_rate
                    except (ValueError, TypeError) as e:
                        log_parse_error(
                            e,
                            data_source="ЦБ РФ SOAP API",
                            data_preview=content[:300],
                            context="Преобразование ставки из текста в число",
                        )

        except ET.ParseError as e:
            log_parse_error(
                e,
                data_source="ЦБ РФ SOAP API",
                data_preview=content[:500],
                context="Парсинг XML ответа от ЦБ РФ",
            )

        # Стратегия 2: Регулярные выражения
        patterns = [
            r'<[^:]*:?keyRate[^>]*>\s*(\d{1,2}[.,]\d{2})\s*<',
            r'<[^:]*:?KeyRate[^>]*>\s*(\d{1,2}[.,]\d{2})\s*<',
        ]

        for i, pattern in enumerate(patterns, 1):
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                rate_str = match.group(1).replace(',', '.')
                try:
                    key_rate = float(rate_str)
                    logger.info(
                        f"✅ Ключевая ставка ЦБ РФ (regex): {key_rate}%"
                    )
                    return key_rate
                except ValueError as e:
                    log_parse_error(
                        e,
                        data_source="ЦБ РФ SOAP API",
                        data_preview=match.group(0),
                        context=f"Преобразование ставки из regex паттерна {i}",
                    )

        # Ничего не нашли
        logger.warning("Не удалось найти ключевую ставку в ответе ЦБ.")
        logger.warning(f"Использую резервное значение: {fallback_rate}%")
        return fallback_rate

    except requests.exceptions.RequestException as e:
        log_network_error(
            e,
            url=url,
            context="Запрос ключевой ставки ЦБ РФ",
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
        logger.warning(f"Использую резервное значение: {fallback_rate}%")
        return fallback_rate

    except Exception as e:
        from error_handler import log_error

        log_error(
            e,
            context="Неожиданная ошибка при получении ставки ЦБ",
            include_stack=True,
        )
        logger.warning(f"Использую резервное значение: {fallback_rate}%")
        return fallback_rate
