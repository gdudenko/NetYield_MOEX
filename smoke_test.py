"""Дымовой тест замороженного приложения: проверяет наличие локальных модулей."""

import sys

print("Smoke test: проверяю модули внутри сборки...")

try:
    import config

    print(f"CONFIG OK: версия {getattr(config, 'APP_VERSION', 'не указана')}")
except Exception as e:
    print(f"CONFIG FAIL: {type(e).__name__}: {e}")
    sys.exit(1)

try:
    import logger

    print("LOGGER OK")
except Exception as e:
    print(f"LOGGER FAIL: {type(e).__name__}: {e}")
    sys.exit(1)

try:
    from services import cbr_rate

    print("SERVICES OK")
except Exception as e:
    print(f"SERVICES FAIL: {type(e).__name__}: {e}")
    sys.exit(1)

print("SMOKE TEST PASSED")
