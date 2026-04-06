"""Tests for pipeline orchestrator."""
import pytest
from datetime import date
from trading_system.pipeline.orchestrator import FactorPipeline
from trading_system.db.engine import get_engine
from sqlalchemy import text


@pytest.fixture
def pipeline():
    return FactorPipeline(get_engine())


@pytest.fixture
def latest_trade_date(pipeline):
    """Get actual latest trading date from DB."""
    with pipeline.engine.connect() as conn:
        row = conn.execute(text("SELECT MAX(trade_date) FROM stock_daily")).fetchone()
        return row[0]


class TestFactorPipeline:
    def test_run_single_stock(self, pipeline, latest_trade_date):
        """Run pipeline for a single well-known stock."""
        count = pipeline.run(latest_trade_date, stock_codes=["600519"])
        assert count >= 1

    def test_run_small_batch(self, pipeline, latest_trade_date):
        """Run for a small batch of stocks."""
        codes = ["600519", "000858", "000001"]
        count = pipeline.run(latest_trade_date, stock_codes=codes)
        assert count >= 1

    def test_output_has_factors(self, pipeline, latest_trade_date):
        """Verify output contains actual factor values."""
        pipeline.run(latest_trade_date, stock_codes=["600519"])

        with pipeline.engine.connect() as conn:
            row = conn.execute(text(
                "SELECT momentum_20d, roe, factors_json FROM factor_cache "
                "WHERE trade_date = :d AND stock_code = '600519'"
            ), {"d": latest_trade_date}).fetchone()

        assert row is not None
        assert row[0] is not None or row[1] is not None
        assert row[2] is not None

    def test_old_date_still_works(self, pipeline):
        """Old date (no valuation data) should still produce results."""
        count = pipeline.run(date(2025, 6, 30), stock_codes=["600519"])
        assert count >= 1
