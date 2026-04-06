"""Recompute factors using backfilled data.

This script identifies missing factors (like pe_ttm) in factor_cache
and recomputes them for all dates between 2023-04-03 and 2026-04-03.
"""
import sys
import codecs
from datetime import date
from sqlalchemy import create_engine, text
from loguru import logger
import time

sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())

from trading_system.pipeline.orchestrator import FactorPipeline

ENGINE_URL = 'postgresql://postgres:postgres@localhost:5432/finance'

def get_dates_to_recompute(start_date: date, end_date: date) -> list[date]:
    """Find dates where factor_cache has no pe_ttm or no main_net_ratio data."""
    engine = create_engine(ENGINE_URL)
    with engine.connect() as conn:
        result = conn.execute(text(
            """
            SELECT trade_date
            FROM factor_cache
            WHERE trade_date BETWEEN :s AND :e
            GROUP BY trade_date
            HAVING COUNT(pe_ttm) = 0 OR COUNT(main_net_ratio) = 0
            ORDER BY trade_date
            """
        ), {"s": start_date, "e": end_date})
        return [row[0] for row in result]

if __name__ == "__main__":
    start_date = date(2023, 4, 3)
    end_date = date(2026, 4, 3)

    dates_to_run = get_dates_to_recompute(start_date, end_date)

    if not dates_to_run:
        logger.info("All factor_cache data appears complete (has PE/Money Flow).")
        sys.exit(0)

    logger.info(f"Recomputing factors for {len(dates_to_run)} dates to pick up newly backfilled data...")

    pipeline = FactorPipeline()
    total = len(dates_to_run)
    t0 = time.time()

    for i, td in enumerate(dates_to_run, 1):
        try:
            count = pipeline.run(td)
            elapsed = time.time() - t0
            avg = elapsed / i
            eta = avg * (total - i)
            logger.info(f"[{i}/{total}] {td} -> {count} rows | avg={avg:.1f}s/day | ETA={eta/60:.0f}min")
        except Exception as e:
            logger.error(f"[{i}/{total}] {td} FAILED: {e}")
            continue

    logger.info(f"Done recomputing! Total time: {(time.time()-t0)/60:.1f} minutes")
