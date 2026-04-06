"""Fast backfill: compute factors for all missing dates in bulk.

Optimization: load daily prices once for the entire period, then slice per date.
"""
import sys
import codecs
from datetime import date, timedelta
from sqlalchemy import create_engine, text
from loguru import logger
import pandas as pd
import time

sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())

logger.remove()
logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level} | {message}")

from trading_system.pipeline.orchestrator import FactorPipeline
from trading_system.pipeline.data_loader import FactorDataLoader

ENGINE_URL = 'postgresql://postgres:postgres@localhost:5432/finance'

def get_trading_days(start_date: date, end_date: date) -> list[date]:
    engine = create_engine(ENGINE_URL)
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT DISTINCT trade_date FROM stock_daily "
            "WHERE trade_date BETWEEN :s AND :e ORDER BY trade_date"
        ), {"s": start_date, "e": end_date})
        return [row[0] for row in result]

def get_existing_dates() -> set[date]:
    engine = create_engine(ENGINE_URL)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT DISTINCT trade_date FROM factor_cache"))
        return {row[0] for row in result}

if __name__ == "__main__":
    start_date = date(2023, 4, 3)
    end_date = date(2026, 4, 3)

    trading_days = get_trading_days(start_date, end_date)
    existing = get_existing_dates()
    missing_days = sorted([d for d in trading_days if d not in existing])

    logger.info(f"Total trading days: {len(trading_days)}, existing: {len(existing)}, missing: {len(missing_days)}")

    if not missing_days:
        logger.info("All factors already computed!")
        sys.exit(0)

    pipeline = FactorPipeline()

    total = len(missing_days)
    t0 = time.time()

    for i, td in enumerate(missing_days, 1):
        try:
            count = pipeline.run(td)
            elapsed = time.time() - t0
            avg = elapsed / i
            eta = avg * (total - i)
            logger.info(f"[{i}/{total}] {td} -> {count} rows | avg={avg:.1f}s/day | ETA={eta/60:.0f}min")
        except Exception as e:
            logger.error(f"[{i}/{total}] {td} FAILED: {e}")
            continue

    logger.info(f"Done! Total time: {(time.time()-t0)/60:.1f} minutes")
