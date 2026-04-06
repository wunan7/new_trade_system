"""Run backtest over historical data."""
import argparse
from datetime import date

from loguru import logger

from trading_system.backtest.engine import BacktestEngine
from trading_system.backtest.report import print_report, export_csv


def main():
    parser = argparse.ArgumentParser(description="Run backtest")
    parser.add_argument("--start", type=str, required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", type=str, required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--capital", type=float, default=1_000_000, help="Initial capital (default 1M)")
    parser.add_argument("--export", action="store_true", help="Export CSV results")
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    engine = BacktestEngine(initial_capital=args.capital)
    result = engine.run(start, end)

    print_report(result)

    if args.export:
        export_csv(result)


if __name__ == "__main__":
    main()
