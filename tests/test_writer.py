"""Tests for factor_cache writer."""
import pytest
from datetime import date
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from trading_system.db.base import Base
from trading_system.db.models import FactorCache
from trading_system.pipeline.writer import write_factor_cache


@pytest.fixture
def pg_session():
    """Use real PostgreSQL session for upsert testing (pg_insert requires PG)."""
    from trading_system.db.engine import get_engine
    engine = get_engine()
    # Ensure table exists
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    # Cleanup test rows
    session.rollback()
    session.close()


class TestWriteFactorCache:
    def test_insert_records(self, pg_session):
        """Insert new records and verify count."""
        test_date = date(2000, 1, 1)  # Use an old date unlikely to conflict
        records = [
            {"trade_date": test_date, "stock_code": "TEST01", "momentum_5d": 0.05, "roe": 12.5},
            {"trade_date": test_date, "stock_code": "TEST02", "momentum_5d": -0.02, "roe": 8.3},
        ]
        count = write_factor_cache(pg_session, FactorCache, records)
        assert count == 2

    def test_upsert_updates(self, pg_session):
        """Upsert same keys with new values should update."""
        test_date = date(2000, 1, 2)
        records = [
            {"trade_date": test_date, "stock_code": "TEST01", "momentum_5d": 0.05},
        ]
        write_factor_cache(pg_session, FactorCache, records)

        # Upsert with new value
        records2 = [
            {"trade_date": test_date, "stock_code": "TEST01", "momentum_5d": 0.10},
        ]
        count = write_factor_cache(pg_session, FactorCache, records2)
        assert count >= 1

    def test_empty_records(self, pg_session):
        """Empty list should return 0."""
        count = write_factor_cache(pg_session, FactorCache, [])
        assert count == 0

    def test_batch_size(self, pg_session):
        """Multiple batches should all be written."""
        test_date = date(2000, 1, 3)
        records = [
            {"trade_date": test_date, "stock_code": f"BATCH{i:02d}", "momentum_5d": 0.01 * i}
            for i in range(5)
        ]
        count = write_factor_cache(pg_session, FactorCache, records, batch_size=2)
        assert count == 5
