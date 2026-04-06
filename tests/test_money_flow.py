"""Tests for money flow factor functions."""
import numpy as np
import pandas as pd
import pytest
from datetime import date, timedelta
from trading_system.factors.money_flow import (
    calc_north_flow_chg,
    calc_north_days,
    calc_main_net_ratio,
    calc_margin_chg_rate,
)


@pytest.fixture
def synthetic_mf():
    """20-day money_flow DataFrame for 3 stocks."""
    codes = ["000001", "000002", "600519"]
    dates = [date(2026, 3, 1) + timedelta(days=i) for i in range(20)]
    rows = []
    np.random.seed(42)
    for code in codes:
        for d in dates:
            rows.append({
                "code": code,
                "trade_date": d,
                "north_net_buy": np.random.uniform(-500, 500),   # 万元
                "main_net_inflow": np.random.uniform(-1000, 1000),  # 万元
                "margin_balance": 1e8 + np.random.uniform(-1e6, 1e6),  # 元
            })
    return pd.DataFrame(rows)


@pytest.fixture
def synthetic_valuation():
    """Valuation DataFrame indexed by code."""
    return pd.DataFrame({
        "circulating_market_cap": [1e10, 5e9, 2e11],  # yuan
        "latest_price": [15.0, 8.0, 1800.0],
    }, index=pd.Index(["000001", "000002", "600519"], name="code"))


@pytest.fixture
def synthetic_daily_amount():
    """Daily amount Series indexed by code (yuan)."""
    return pd.Series(
        [5e8, 3e8, 2e9],
        index=pd.Index(["000001", "000002", "600519"], name="code"),
    )


class TestNorthFlowChg:
    def test_basic_computation(self, synthetic_mf, synthetic_valuation):
        result = calc_north_flow_chg(synthetic_mf, synthetic_valuation, n=5)
        assert len(result) == 3
        assert result.notna().all()

    def test_empty_mf(self, synthetic_valuation):
        result = calc_north_flow_chg(pd.DataFrame(), synthetic_valuation)
        assert result.empty

    def test_empty_valuation(self, synthetic_mf):
        result = calc_north_flow_chg(synthetic_mf, pd.DataFrame())
        assert result.empty

    def test_missing_cap_column(self, synthetic_mf):
        val = pd.DataFrame({"latest_price": [10]}, index=pd.Index(["000001"], name="code"))
        result = calc_north_flow_chg(synthetic_mf, val)
        assert result.empty

    def test_positive_buy_positive_result(self):
        """Consistent positive north buy should give positive ratio."""
        mf = pd.DataFrame({
            "code": ["000001"] * 5,
            "trade_date": [date(2026, 3, i) for i in range(1, 6)],
            "north_net_buy": [100.0] * 5,
            "main_net_inflow": [0.0] * 5,
            "margin_balance": [0.0] * 5,
        })
        val = pd.DataFrame({
            "circulating_market_cap": [1e10],  # yuan = 1e6 万元
        }, index=pd.Index(["000001"], name="code"))
        result = calc_north_flow_chg(mf, val, n=5)
        assert result["000001"] > 0


class TestNorthDays:
    def test_all_positive(self, synthetic_mf):
        """Override all north_net_buy to positive."""
        mf = synthetic_mf.copy()
        mf["north_net_buy"] = 100.0
        result = calc_north_days(mf, n=20)
        assert all(v == 1.0 for v in result.values)

    def test_all_negative(self, synthetic_mf):
        mf = synthetic_mf.copy()
        mf["north_net_buy"] = -100.0
        result = calc_north_days(mf, n=20)
        assert all(v == 0.0 for v in result.values)

    def test_mixed(self):
        """Half positive, half negative -> ratio ~0.5."""
        mf = pd.DataFrame({
            "code": ["000001"] * 10,
            "trade_date": [date(2026, 3, i) for i in range(1, 11)],
            "north_net_buy": [100, -100, 100, -100, 100, -100, 100, -100, 100, -100],
            "main_net_inflow": [0] * 10,
            "margin_balance": [0] * 10,
        })
        result = calc_north_days(mf, n=10)
        assert result["000001"] == 0.5

    def test_empty(self):
        result = calc_north_days(pd.DataFrame())
        assert result.empty


class TestMainNetRatio:
    def test_basic(self, synthetic_mf, synthetic_daily_amount):
        result = calc_main_net_ratio(synthetic_mf, synthetic_daily_amount)
        assert len(result) == 3
        assert result.notna().all()

    def test_empty_mf(self, synthetic_daily_amount):
        result = calc_main_net_ratio(pd.DataFrame(), synthetic_daily_amount)
        assert result.empty

    def test_empty_amount(self, synthetic_mf):
        result = calc_main_net_ratio(synthetic_mf, pd.Series(dtype=float))
        assert result.empty

    def test_zero_amount_gives_nan(self):
        """Zero trading amount should produce NaN."""
        mf = pd.DataFrame({
            "code": ["000001"],
            "trade_date": [date(2026, 3, 1)],
            "north_net_buy": [0],
            "main_net_inflow": [500.0],
            "margin_balance": [0],
        })
        amount = pd.Series([0.0], index=pd.Index(["000001"], name="code"))
        result = calc_main_net_ratio(mf, amount)
        assert np.isnan(result["000001"])


class TestMarginChgRate:
    def test_basic(self, synthetic_mf):
        result = calc_margin_chg_rate(synthetic_mf, n=5)
        assert len(result) == 3

    def test_increasing_margin(self):
        """Margin balance growing should give positive rate."""
        mf = pd.DataFrame({
            "code": ["000001"] * 10,
            "trade_date": [date(2026, 3, i) for i in range(1, 11)],
            "north_net_buy": [0] * 10,
            "main_net_inflow": [0] * 10,
            "margin_balance": [1e8 + i * 1e6 for i in range(10)],
        })
        result = calc_margin_chg_rate(mf, n=5)
        assert result["000001"] > 0

    def test_decreasing_margin(self):
        """Margin balance shrinking should give negative rate."""
        mf = pd.DataFrame({
            "code": ["000001"] * 10,
            "trade_date": [date(2026, 3, i) for i in range(1, 11)],
            "north_net_buy": [0] * 10,
            "main_net_inflow": [0] * 10,
            "margin_balance": [1e8 - i * 1e6 for i in range(10)],
        })
        result = calc_margin_chg_rate(mf, n=5)
        assert result["000001"] < 0

    def test_empty(self):
        result = calc_margin_chg_rate(pd.DataFrame())
        assert result.empty

    def test_single_date(self):
        """Only one date means no change can be computed."""
        mf = pd.DataFrame({
            "code": ["000001"],
            "trade_date": [date(2026, 3, 1)],
            "north_net_buy": [0],
            "main_net_inflow": [0],
            "margin_balance": [1e8],
        })
        result = calc_margin_chg_rate(mf, n=5)
        assert result.empty
