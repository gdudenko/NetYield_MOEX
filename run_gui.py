"""
Точка входа для запуска NetYield MOEX с графическим интерфейсом.
"""

from logger import get_logger

logger = get_logger(__name__)


def main():
    logger.info("🖥️ Запуск NetYield MOEX (GUI-режим)")
    try:
        from ui.gui_app import run_gui

        run_gui()
    except ImportError as e:
        logger.error(f"Ошибка импорта GUI модулей: {e}")
        print(f"\n❌ Ошибка: {e}")
        print("Убедитесь, что установлен customtkinter:")
        print("   pip install customtkinter")
    except Exception as e:
        logger.error(f"Критическая ошибка GUI: {e}", exc_info=True)
        print(f"\n❌ Критическая ошибка: {e}")


if __name__ == "__main__":
    main()
