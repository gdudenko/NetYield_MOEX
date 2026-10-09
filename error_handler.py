"""
Централизованный обработчик ошибок для проекта NetYield MOEX.

Предоставляет функции для логирования исключений с полной информацией:
- Текстом ошибки
- Трейсбеком (stack trace)
- Стеком вызова функций
- Контекстом выполнения

Использование:
    from error_handler import log_error, log_network_error, log_parse_error

    try:
        # код
    except Exception as e:
        log_error(e, context="Загрузка данных с Мосбиржи")
"""

import logging
from typing import Any, Optional

from logger import get_logger

logger = get_logger(__name__)

PREVIEW_LIMIT = 500


def _build_extra_data(**fields: Any) -> dict:
    """Собирает словарь доп. данных, выкидывая пустые значения.

    Пустые поля в лог не пишем: запись «response_status: None» только
    шумит и мешает читать лог. Сами специализированные логгеры сводятся
    к общему log_error через этот хелпер.
    """
    return {
        key: value
        for key, value in fields.items()
        if value is not None and value != '' and value != {}
    }


def _trim_preview(text: Optional[str]) -> Optional[str]:
    """Обрезает длинный ответ API, чтобы лог не разрастался."""
    if not text:
        return None
    return text[:PREVIEW_LIMIT]


def log_error(
    error: Exception,
    context: str = "",
    extra_data: Optional[dict] = None,
    include_stack: bool = False,
    level: int = logging.ERROR,
):
    """
    Логирует ошибку с полной информацией.

    Args:
        error: Исключение, которое нужно залогировать.
        context: Описание контекста, в котором произошла ошибка.
        extra_data: Дополнительные данные для логирования (словарь).
        include_stack: Включать ли полный стек вызова функций.
        level: Уровень логирования (ERROR, CRITICAL и т.д.).
    """
    # Формируем сообщение
    message_parts = []

    if context:
        message_parts.append(f"Контекст: {context}")

    message_parts.append(f"Ошибка: {type(error).__name__}: {error}")

    if extra_data:
        message_parts.append(f"Дополнительные данные: {extra_data}")

    message = " | ".join(message_parts)

    # Логируем с трейсбеком
    if include_stack:
        logger.log(level, message, exc_info=True, stack_info=True)
    else:
        logger.log(level, message, exc_info=True)


def log_network_error(
    error: Exception,
    url: str = "",
    context: str = "Сетевой запрос",
    response_status: Optional[int] = None,
    response_content: Optional[str] = None,
):
    """
    Специализированный логгер для сетевых ошибок.

    Args:
        error: Исключение сети (RequestException и т.п.).
        url: URL, к которому был запрос.
        context: Описание операции.
        response_status: HTTP статус ответа (если есть).
        response_content: Содержимое ответа (обрезается до 500 символов).
    """
    log_error(
        error,
        context=context,
        extra_data=_build_extra_data(
            url=url,
            status_code=response_status,
            response_preview=_trim_preview(response_content),
        ),
    )


def log_parse_error(
    error: Exception,
    data_source: str = "",
    data_preview: Optional[str] = None,
    context: str = "Парсинг данных",
):
    """
    Специализированный логгер для ошибок парсинга (XML, JSON и т.п.).

    Args:
        error: Исключение парсинга (ParseError, ValueError и т.п.).
        data_source: Источник данных (URL, файл и т.п.).
        data_preview: Превью данных, которые не удалось распарсить.
        context: Описание операции.
    """
    log_error(
        error,
        context=context,
        extra_data=_build_extra_data(
            source=data_source,
            data_preview=_trim_preview(data_preview),
        ),
    )


def log_calculation_error(
    error: Exception,
    bond_id: str = "",
    calculation_type: str = "",
    input_data: Optional[dict] = None,
    context: str = "Расчёт доходности",
):
    """
    Специализированный логгер для ошибок расчёта.

    Args:
        error: Исключение расчёта.
        bond_id: Идентификатор облигации (тикер).
        calculation_type: Тип расчёта (maturity, sale и т.п.).
        input_data: Входные данные расчёта.
        context: Описание операции.
    """
    log_error(
        error,
        context=context,
        extra_data=_build_extra_data(
            bond_id=bond_id,
            calculation_type=calculation_type,
            input_data=input_data,
        ),
    )