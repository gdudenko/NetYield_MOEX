"""
Настройка логирования для проекта NetYield MOEX.

Использование в любом модуле:
    from logger import get_logger
    logger = get_logger(__name__)

    logger.debug("Детальная информация для отладки")
    logger.info("Основное событие")
    logger.warning("Нештатная ситуация")
    logger.error("Ошибка")
"""

import logging
import sys
import config


def get_logger(name: str) -> logging.Logger:
    """
    Создаёт или возвращает настроенный логгер для модуля.

    Args:
        name: Имя модуля (обычно передаётся __name__).

    Returns:
        Настроенный логгер.
    """
    logger = logging.getLogger(name)

    # Если логгер уже настроен — возвращаем как есть
    if logger.handlers:
        return logger

    # Базовый уровень (самый детальный)
    logger.setLevel(logging.DEBUG)

    # Предотвращаем дублирование логов в корневой логгер
    logger.propagate = False

    # --------------------------------------------------------
    # Хендлер 1: Консоль (INFO и выше)
    # --------------------------------------------------------
    console_handler = logging.StreamHandler(sys.stdout)
    console_level = getattr(logging, config.CONSOLE_LOG_LEVEL, logging.INFO)
    console_handler.setLevel(console_level)

    console_formatter = logging.Formatter(
        config.LOG_CONSOLE_FORMAT, datefmt=config.LOG_DATE_FORMAT
    )
    console_handler.setFormatter(console_formatter)

    # --------------------------------------------------------
    # Хендлер 2: Файл (DEBUG и выше, полная история)
    # --------------------------------------------------------
    file_handler = logging.FileHandler(
        config.LOG_FILE, encoding='utf-8', mode='a'  # Дописывать в конец файла
    )
    file_level = getattr(logging, config.FILE_LOG_LEVEL, logging.DEBUG)
    file_handler.setLevel(file_level)

    file_formatter = logging.Formatter(
        config.LOG_FILE_FORMAT, datefmt=config.LOG_DATE_FORMAT
    )
    file_handler.setFormatter(file_formatter)

    # --------------------------------------------------------
    # Добавляем хендлеры к логгеру
    # --------------------------------------------------------
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger
