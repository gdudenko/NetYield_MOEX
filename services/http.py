"""
Общий HTTP-слой для внешних сервисов.

ЦБ РФ и Мосбиржа отдавали почти одинаковую обработку ошибок: один и тот же
raise_for_status, один и тот же разбор RequestException с попыткой достать
код ответа и тело, один и тот же «неожиданный» except. Здесь эта логика
одна, а сервисы занимаются только своим форматом данных.
"""

from typing import Optional

import requests

from error_handler import log_error, log_network_error
from logger import get_logger

logger = get_logger(__name__)


def _describe_response(error: Exception) -> tuple[Optional[int], Optional[str]]:
    """Достаёт из исключения код и тело ответа, если они доступны."""
    response = getattr(error, 'response', None)
    if response is None:
        return None, None
    return getattr(response, 'status_code', None), getattr(response, 'text', None)


def request_with_logging(
    method: str,
    url: str,
    *,
    context: str,
    **kwargs,
) -> Optional[requests.Response]:
    """Делает HTTP-запрос, логируя любую ошибку.

    Args:
        method: HTTP-метод ('GET', 'POST', ...).
        url: Адрес запроса.
        context: Описание операции для лога.
        **kwargs: Аргументы requests (params, data, headers, timeout).

    Returns:
        Response с успешным статусом или None, если запрос не удался.
    """
    try:
        response = requests.request(method, url, **kwargs)
        response.raise_for_status()
        logger.debug(f"{context}: статус ответа {response.status_code}")
        return response

    except requests.exceptions.RequestException as e:
        status, body = _describe_response(e)
        log_network_error(
            e,
            url=url,
            context=context,
            response_status=status,
            response_content=body,
        )
        return None

    except Exception as e:
        log_error(e, context=context, include_stack=True)
        return None