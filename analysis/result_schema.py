"""
Схема результатов анализа — единственный источник названий колонок.

Раньше консольный и графический выводы собирали одни и те же данные
в двух разных наборах колонок с разными названиями и разным округлением.
Схема описывает результат один раз, а оба интерфейса берут из неё и
подписи, и ширины, и порядок, и округление.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ResultColumn:
    """Описание одного столбца таблицы результатов.

    Attributes:
        key: Имя столбца в DataFrame (и заголовок по умолчанию).
        width: Ширина столбца в GUI (в символах).
        decimals: Знаков после запятой. None — значение не округлять.
        is_integer: Значение приводится к int (кол-во сделок, дней).
        numeric: Столбец сортируется как число, а не как строка.
    """

    key: str
    width: int
    decimals: int | None = None
    is_integer: bool = False
    numeric: bool = False


RESULT_COLUMNS: tuple[ResultColumn, ...] = (
    ResultColumn('Тикер', 120),
    ResultColumn('Тип', 80),
    ResultColumn('Эмитент', 150),
    ResultColumn('Тип купона', 120),
    ResultColumn('Цена (%)', 90, decimals=2, numeric=True),
    ResultColumn('Купон (%)', 90, decimals=2, numeric=True),
    ResultColumn('Погашение', 100),
    ResultColumn('Оферта', 100),
    ResultColumn('Статус', 100),
    ResultColumn('Дней', 60, is_integer=True, numeric=True),
    ResultColumn('Сделок', 70, is_integer=True, numeric=True),
    ResultColumn('Оборот (тыс)', 100, decimals=1, numeric=True),
    ResultColumn('Чист. доход (₽)', 120, decimals=2, numeric=True),
    ResultColumn('Доход. за период (%)', 150, decimals=2, numeric=True),
    ResultColumn('Годовая доход. (%)', 150, decimals=2, numeric=True),
)

COLUMN_KEYS: tuple[str, ...] = tuple(col.key for col in RESULT_COLUMNS)

# Столбец, по которому консоль сортирует результат по убыванию.
YIELD_COLUMN = 'Доход. за период (%)'


def build_row(raw: dict) -> dict:
    """Приводит сырую строку расчёта к схеме: порядок, типы, округление.

    Args:
        raw: Словарь «как посчитал калькулятор», ключи произвольные.

    Returns:
        Словарь с ключами из COLUMN_KEYS в нужном порядке.
    """
    row = {}
    for col in RESULT_COLUMNS:
        value = raw[col.key]
        if col.is_integer:
            row[col.key] = int(value)
        elif col.decimals is not None:
            row[col.key] = round(value, col.decimals)
        else:
            row[col.key] = value
    return row