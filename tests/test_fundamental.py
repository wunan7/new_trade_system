"""Tests for fundamental factor functions."""
import numpy as np
import pandas as pd
import pytest
from decimal import Decimal
from trading_system.factors.fundamental import (
    get_roe, get_gross_margin, get_net_margin, get_debt_ratio,
    get_revenue_growth, get_profit_growth,
    get_pe_ttm, get_pb, get_ps_ttm,
    calc_ocf_to_profit, calc_accrual_ratio, calc_goodwill_ratio, calc_dividend_yield,
)


@pytest.fixture
def summary_df():
    return pd.DataFrame({
        "roe": [12.5, Decimal("8.3"), None],
        "gross_margin": [35.2, 22.1, 91.5],
        "net_margin": [18.5, 10.2, 52.3],
        "debt_to_assets": [88.5, 65.3, 18.2],
        "revenue_growth": [5.2, -3.1, 15.8],
        "earnings_growth": [8.1, -12.5, 20.3],
    }, index=pd.Index(["000001", "000002", "600519"], name="code"))


@pytest.fixture
def valuation_df():
    return pd.DataFrame({
        "pe_ttm": [Decimal("15.2"), Decimal("22.8"), Decimal("35.1")],
        "pb": [1.2, 2.5, 12.8],
        "ps_ttm": [3.1, 5.2, 18.5],
        "latest_price": [12.5, 45.0, 1800.0],
    }, index=pd.Index(["000001", "000002", "600519"], name="code"))


class TestDirectExtraction:
    def test_get_roe(self, summary_df):
        result = get_roe(summary_df)
        assert result["000001"] == 12.5
        assert abs(result["000002"] - 8.3) < 0.01  # Decimal conversion
        assert np.isnan(result["600519"])  # None -> NaN

    def test_get_gross_margin(self, summary_df):
        result = get_gross_margin(summary_df)
        assert result["600519"] == 91.5

    def test_get_revenue_growth(self, summary_df):
        result = get_revenue_growth(summary_df)
        assert result["000002"] == -3.1  # Negative growth OK

    def test_empty_df_returns_empty(self):
        result = get_roe(pd.DataFrame())
        assert len(result) == 0

    def test_get_pe_ttm(self, valuation_df):
        result = get_pe_ttm(valuation_df)
        assert abs(result["000001"] - 15.2) < 0.01

    def test_get_pe_ttm_empty(self):
        result = get_pe_ttm(pd.DataFrame())
        assert len(result) == 0


class TestComputedFactors:
    def test_ocf_to_profit_equal(self):
        """When OCF == NP, ratio should be 1.0."""
        cashflow = pd.DataFrame(
            {"act_cash_flow_net": [100, 200]},
            index=pd.Index(["A", "B"], name="code")
        )
        income = pd.DataFrame(
            {"net_profit": [100, 200]},
            index=pd.Index(["A", "B"], name="code")
        )
        result = calc_ocf_to_profit(cashflow, income)
        assert np.isclose(result["A"], 1.0)
        assert np.isclose(result["B"], 1.0)

    def test_ocf_to_profit_zero_np(self):
        """Zero net profit -> NaN."""
        cashflow = pd.DataFrame(
            {"act_cash_flow_net": [100]},
            index=pd.Index(["A"], name="code")
        )
        income = pd.DataFrame(
            {"net_profit": [0]},
            index=pd.Index(["A"], name="code")
        )
        result = calc_ocf_to_profit(cashflow, income)
        assert np.isnan(result["A"])

    def test_goodwill_ratio_none_goodwill(self):
        """Missing goodwill -> ratio = 0."""
        balance = pd.DataFrame({
            "goodwill": [None, 100],
            "holder_equity_total": [1000, 1000],
        }, index=pd.Index(["A", "B"], name="code"))
        result = calc_goodwill_ratio(balance)
        assert result["A"] == 0.0
        assert np.isclose(result["B"], 0.1)

    def test_dividend_yield(self):
        dividend = pd.DataFrame(
            {"dividend_per_10": [20.0]},  # 2元/股
            index=pd.Index(["600519"], name="code")
        )
        valuation = pd.DataFrame(
            {"latest_price": [1800.0]},
            index=pd.Index(["600519"], name="code")
        )
        result = calc_dividend_yield(dividend, valuation)
        expected = 2.0 / 1800.0
        assert abs(result["600519"] - expected) < 0.0001

    def test_dividend_yield_missing_price(self):
        dividend = pd.DataFrame(
            {"dividend_per_10": [20.0]},
            index=pd.Index(["A"], name="code")
        )
        valuation = pd.DataFrame(
            {"latest_price": [0.0]},  # zero price
            index=pd.Index(["A"], name="code")
        )
        result = calc_dividend_yield(dividend, valuation)
        assert np.isnan(result["A"])

    def test_accrual_ratio(self):
        income = pd.DataFrame(
            {"net_profit": [100]},
            index=pd.Index(["A"], name="code")
        )
        cashflow = pd.DataFrame(
            {"act_cash_flow_net": [80]},
            index=pd.Index(["A"], name="code")
        )
        balance = pd.DataFrame(
            {"assets_total": [1000]},
            index=pd.Index(["A"], name="code")
        )
        result = calc_accrual_ratio(income, cashflow, balance)
        # (100 - 80) / 1000 = 0.02
        assert abs(result["A"] - 0.02) < 0.001

    def test_empty_inputs(self):
        empty = pd.DataFrame()
        assert len(calc_ocf_to_profit(empty, empty)) == 0
        assert len(calc_goodwill_ratio(empty)) == 0
        assert len(calc_dividend_yield(empty, empty)) == 0
