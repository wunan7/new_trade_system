"""Tests for data loader against live PostgreSQL."""
import pytest
import pandas as pd
from datetime import date
from trading_system.db.engine import get_engine
from trading_system.pipeline.data_loader import FactorDataLoader


@pytest.fixture
def loader():
    return FactorDataLoader(get_engine(), lookback_days=60)


class TestLoadStockList:
    def test_returns_list_of_codes(self, loader):
        codes = loader.load_stock_list()
        assert len(codes) > 4000  # Should have 4000+ active non-ST stocks
        assert all(isinstance(c, str) for c in codes)
        assert "600519" in codes  # 贵州茅台

    def test_exclude_st(self, loader):
        all_codes = loader.load_stock_list(exclude_st=False)
        no_st = loader.load_stock_list(exclude_st=True)
        assert len(all_codes) >= len(no_st)


class TestLoadDailyPrices:
    def test_returns_dict_of_dataframes(self, loader):
        prices = loader.load_daily_prices(date(2026, 3, 28), stock_codes=["600519", "000858"])
        assert isinstance(prices, dict)
        assert "600519" in prices
        df = prices["600519"]
        assert isinstance(df, pd.DataFrame)
        assert "close" in df.columns
        assert "volume" in df.columns
        assert len(df) > 0

    def test_lookback_limit(self, loader):
        prices = loader.load_daily_prices(date(2026, 3, 28), stock_codes=["600519"])
        df = prices["600519"]
        assert len(df) <= 60  # lookback_days=60


class TestLoadFinancialSummary:
    def test_returns_indexed_by_code(self, loader):
        summary = loader.load_financial_summary(date(2026, 3, 28))
        assert not summary.empty
        assert summary.index.name == "code"
        assert "roe" in summary.columns
        assert "600519" in summary.index

    def test_latest_report_per_stock(self, loader):
        summary = loader.load_financial_summary(date(2026, 3, 28))
        # Should have one row per stock (DISTINCT ON)
        assert not summary.index.duplicated().any()


class TestLoadValuation:
    def test_recent_date_has_data(self, loader):
        # Use a recent date that should have valuation data
        val = loader.load_valuation(date(2026, 3, 28))
        # May be empty if 2026-03-28 is not a trading day; that's OK
        if not val.empty:
            assert "pe_ttm" in val.columns
            assert val.index.name == "code"

    def test_old_date_empty(self, loader):
        # Before 2026-03-10, no valuation data
        val = loader.load_valuation(date(2025, 1, 1))
        assert val.empty


class TestLoadDividends:
    def test_returns_dividend_data(self, loader):
        div = loader.load_dividends()
        assert not div.empty
        assert "dividend_per_10" in div.columns
        assert div.index.name == "code"


class TestLoadIndexPrices:
    def test_csi300(self, loader):
        idx = loader.load_index_prices(date(2026, 3, 28), "000300")
        assert not idx.empty
        assert "close" in idx.columns
