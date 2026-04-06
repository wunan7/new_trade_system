"""Tests for backtest metrics calculation."""
import pytest
import numpy as np
from datetime import date
from trading_system.backtest.metrics import calc_metrics, BacktestResult


class TestCalcMetrics:
    def _make_navs(self, values, start=date(2026, 1, 2)):
        """Helper: create daily_navs list from a value sequence."""
        from datetime import timedelta
        return [
            {"date": start + timedelta(days=i), "total_value": v, "benchmark_close": 4500 + i}
            for i, v in enumerate(values)
        ]

    def test_basic_positive_return(self):
        navs = self._make_navs([1_000_000, 1_010_000, 1_020_000, 1_030_000])
        result = calc_metrics(navs, [], 1_000_000)
        assert result.total_return == pytest.approx(0.03, abs=0.001)
        assert result.trading_days == 4

    def test_negative_return(self):
        navs = self._make_navs([1_000_000, 990_000, 980_000])
        result = calc_metrics(navs, [], 1_000_000)
        assert result.total_return == pytest.approx(-0.02, abs=0.001)

    def test_max_drawdown(self):
        navs = self._make_navs([1_000_000, 1_100_000, 900_000, 950_000])
        result = calc_metrics(navs, [], 1_000_000)
        # Peak 1.1M, trough 900K → drawdown = 200K/1.1M ≈ 18.2%
        assert result.max_drawdown == pytest.approx(0.1818, abs=0.01)

    def test_no_drawdown(self):
        navs = self._make_navs([1_000_000, 1_010_000, 1_020_000])
        result = calc_metrics(navs, [], 1_000_000)
        assert result.max_drawdown == 0.0

    def test_sharpe_positive(self):
        # Steady growth → positive Sharpe
        values = [1_000_000 * (1.0003 ** i) for i in range(100)]
        navs = self._make_navs(values)
        result = calc_metrics(navs, [], 1_000_000)
        assert result.sharpe_ratio > 0

    def test_trade_stats(self):
        navs = self._make_navs([1_000_000, 1_050_000])
        trades = [
            {"date": date(2026, 1, 2), "code": "000001", "direction": "BUY",
             "price": 10, "shares": 1000, "amount": 10000, "cost": 5},
            {"date": date(2026, 1, 3), "code": "000001", "direction": "SELL",
             "price": 11, "shares": 1000, "amount": 11000, "cost": 15,
             "pnl_pct": 0.10, "hold_days": 1, "reason": "take_profit"},
            {"date": date(2026, 1, 3), "code": "000002", "direction": "SELL",
             "price": 9, "shares": 500, "amount": 4500, "cost": 10,
             "pnl_pct": -0.05, "hold_days": 3, "reason": "stop_loss"},
        ]
        result = calc_metrics(navs, trades, 1_000_000)
        assert result.total_trades == 3
        assert result.win_rate == pytest.approx(0.5, abs=0.01)  # 1 win / 2 sells
        assert result.avg_win_pct == pytest.approx(0.10, abs=0.001)
        assert result.avg_loss_pct == pytest.approx(-0.05, abs=0.001)

    def test_empty_navs(self):
        result = calc_metrics([], [], 1_000_000)
        assert result.trading_days == 0
        assert result.total_return == 0.0

    def test_profit_factor(self):
        navs = self._make_navs([1_000_000, 1_050_000])
        trades = [
            {"date": date(2026, 1, 2), "code": "A", "direction": "SELL",
             "price": 10, "shares": 100, "pnl_pct": 0.20, "hold_days": 5},
            {"date": date(2026, 1, 2), "code": "B", "direction": "SELL",
             "price": 10, "shares": 100, "pnl_pct": -0.10, "hold_days": 3},
        ]
        result = calc_metrics(navs, trades, 1_000_000)
        # profit_factor = 0.20 / 0.10 = 2.0
        assert result.profit_factor == pytest.approx(2.0, abs=0.01)

    def test_drawdown_duration(self):
        # Peak at index 1, then 3 days of drawdown, then recovery
        navs = self._make_navs([1_000_000, 1_100_000, 1_050_000, 1_000_000, 950_000, 1_100_000])
        result = calc_metrics(navs, [], 1_000_000)
        assert result.max_drawdown_duration >= 3
