"""CLI: Compute factors for a given date or date range."""
import argparse
import sys
from datetime import date, datetime

from loguru import logger
from trading_system.pipeline.orchestrator import FactorPipeline


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main():
    parser = argparse.ArgumentParser(description="Compute and cache factor values")
    parser.add_argument("--date", type=parse_date, help="Single date (YYYY-MM-DD)")
    parser.add_argument("--start", type=parse_date, help="Range start date")
    parser.add_argument("--end", type=parse_date, help="Range end date")
    parser.add_argument("--codes", type=str, help="Comma-separated stock codes (default: all)")

    args = parser.parse_args()
    stock_codes = args.codes.split(",") if args.codes else None

    pipeline = FactorPipeline()

    if args.date:
        count = pipeline.run(args.date, stock_codes=stock_codes)
        logger.info(f"Done: {count} rows for {args.date}")
    elif args.start and args.end:
        count = pipeline.run_range(args.start, args.end, stock_codes=stock_codes)
        logger.info(f"Done: {count} total rows for {args.start} to {args.end}")
    else:
        # Default: latest trading day
        from sqlalchemy import text
        with pipeline.engine.connect() as conn:
            row = conn.execute(text("SELECT MAX(trade_date) FROM stock_daily")).fetchone()
            latest = row[0]
        logger.info(f"No date specified, using latest: {latest}")
        count = pipeline.run(latest, stock_codes=stock_codes)
        logger.info(f"Done: {count} rows for {latest}")


if __name__ == "__main__":
    main()
