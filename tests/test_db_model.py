"""Test FactorCache model schema"""
from sqlalchemy import create_engine, inspect
from trading_system.db.base import Base
from trading_system.db.models import FactorCache


def test_factor_cache_columns():
    """Verify all expected columns exist"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    columns = {c["name"] for c in inspector.get_columns("factor_cache")}

    expected_technical = {"momentum_5d", "momentum_20d", "momentum_60d",
                         "volatility_20d", "volatility_60d", "atr_14d",
                         "volume_ratio_5d", "turnover_dev", "macd_signal",
                         "adx", "bb_width", "rs_vs_index", "obv_slope"}
    expected_fundamental = {"roe", "gross_margin", "net_margin", "debt_ratio",
                           "revenue_growth", "profit_growth", "ocf_to_profit",
                           "accrual_ratio", "goodwill_ratio", "pe_ttm", "pb",
                           "ps_ttm", "dividend_yield"}
    expected_meta = {"trade_date", "stock_code", "factors_json", "updated_at"}

    all_expected = expected_technical | expected_fundamental | expected_meta
    assert all_expected.issubset(columns), f"Missing: {all_expected - columns}"


def test_factor_cache_primary_key():
    """Verify composite PK on (trade_date, stock_code)"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    pk = inspector.get_pk_constraint("factor_cache")
    assert set(pk["constrained_columns"]) == {"trade_date", "stock_code"}
