"""CLI: Generate trading signals for a given date or date range."""
import argparse
from datetime import date, datetime

from loguru import logger
from trading_system.signals.generator import SignalGenerator


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main():
    parser = argparse.ArgumentParser(description="Generate trading signals")
    parser.add_argument("--date", type=parse_date, help="Single date (YYYY-MM-DD)")
    parser.add_argument("--start", type=parse_date, help="Range start date")
    parser.add_argument("--end", type=parse_date, help="Range end date")
    parser.add_argument("--codes", type=str, help="Comma-separated stock codes (default: all)")

    args = parser.parse_args()
    stock_codes = args.codes.split(",") if args.codes else None

    generator = SignalGenerator()

    if args.date:
        count = generator.run(args.date, stock_codes=stock_codes)
        logger.info(f"Done: {count} signals for {args.date}")
    elif args.start and args.end:
        from sqlalchemy import text
        with generator.engine.connect() as conn:
            result = conn.execute(text(
                "SELECT DISTINCT trade_date FROM stock_daily "
                "WHERE trade_date BETWEEN :start AND :end "
                "ORDER BY trade_date"
            ), {"start": args.start, "end": args.end})
            trading_days = [row[0] for row in result]

        total = 0
        for i, td in enumerate(trading_days):
            logger.info(f"[{i+1}/{len(trading_days)}] Processing {td}")
            count = generator.run(td, stock_codes=stock_codes)
            total += count

        logger.info(f"Done: {total} total signals across {len(trading_days)} days")
    else:
        from sqlalchemy import text
        with generator.engine.connect() as conn:
            row = conn.execute(text("SELECT MAX(trade_date) FROM stock_daily")).fetchone()
            latest = row[0]
        logger.info(f"No date specified, using latest: {latest}")
        count = generator.run(latest, stock_codes=stock_codes)
        logger.info(f"Done: {count} signals for {latest}")


if __name__ == "__main__":
    main()
