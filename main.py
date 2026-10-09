"""
NetYield MOEX — калькулятор доходности облигаций.
"""

import app_config as config
from analysis.pipeline import AnalysisError, run_analysis
from logger import get_logger
from services.cbr_rate import get_cbr_key_rate
from ui.console import get_user_scenario, print_results

logger = get_logger(__name__)


def main() -> None:
    """Точка входа консольного режима."""
    logger.info("🚀 Запуск NetYield MOEX")

    current_cbr_rate = get_cbr_key_rate(
        fallback_rate=config.FLOATING_COUPON_RATE
    )

    print("\n" + "=" * 40)
    print(f"🏦 Ключевая ставка ЦБ РФ сегодня: {current_cbr_rate}%")
    print("=" * 40)

    buy_date, sell_date, scenario_key = get_user_scenario()

    try:
        res_df = run_analysis(
            buy_date, sell_date, scenario_key, current_cbr_rate
        )
    except AnalysisError as e:
        logger.error(f"Анализ не выполнен: {e}")
        print(f"\n❌ {e}")
        return

    print_results(
        res_df,
        (sell_date - buy_date).days,
        buy_date,
        sell_date,
        current_cbr_rate,
        scenario_key,
    )

    logger.info("✅ Работа завершена")


if __name__ == "__main__":
    main()