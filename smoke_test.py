# Страховка от кодировок консоли раннера
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

print("Smoke test: checking bundled modules...")

try:
    import config

    print("CONFIG OK: version", getattr(config, "APP_VERSION", "not-set"))
except Exception as e:
    print("CONFIG FAIL:", type(e).__name__, e)
    sys.exit(1)

try:
    import logger

    print("LOGGER OK")
except Exception as e:
    print("LOGGER FAIL:", type(e).__name__, e)
    sys.exit(1)

try:
    from services import cbr_rate

    print("SERVICES OK")
except Exception as e:
    print("SERVICES FAIL:", type(e).__name__, e)
    sys.exit(1)

print("SMOKE TEST PASSED")
