"""Tests for cost model, stop loss, drawdown monitor, and position sizer."""
import pytest
from datetime import date, timedelta

from trading_system.execution.cost_model import calc_trade_cost
from trading_system.risk.stop_loss import StopLossCalculator
from trading_system.risk.drawdown_monitor import DrawdownMonitor, DrawdownLevel
from trading_system.risk.position_sizer import PositionSizer, PositionOrder
from trading_system.strategies.base import Signal, MarketState


# ============================================================
# Cost Model Tests
# ============================================================
class TestCostModel:
    def test_buy_no_stamp_tax(self):
        cost = calc_trade_cost(10.0, 1000, "BUY")
        assert cost["stamp_tax"] == 0.0
        assert cost["commission"] > 0
        assert cost["slippage"] > 0

    def test_sell_has_stamp_tax(self):
        cost = calc_trade_cost(10.0, 1000, "SELL")
        # 10 * 1000 * 0.001 = 10.0
        assert cost["stamp_tax"] == 10.0

    def test_minimum_commission(self):
        cost = calc_trade_cost(1.0, 100, "BUY")
        # 1 * 100 * 0.00025 = 0.025 < 5
        assert cost["commission"] == 5.0

    def test_large_order(self):
        cost = calc_trade_cost(100.0, 10000, "SELL")
        amount = 100.0 * 10000
        assert cost["commission"] == round(amount * 0.00025, 2)
        assert cost["stamp_tax"] == round(amount * 0.001, 2)
        assert cost["total"] == cost["commission"] + cost["stamp_tax"] + cost["slippage"]


# ============================================================
# Stop Loss Tests
# ============================================================
class TestStopLoss:
    def setup_method(self):
        self.calc = StopLossCalculator()

    def test_initial_momentum(self):
        sl, tp = self.calc.calc_initial("momentum", 100.0)
        assert sl == 95.0   # -5%
        assert tp == 110.0  # +10%

    def test_initial_value(self):
        sl, tp = self.calc.calc_initial("value", 100.0)
        assert sl == 88.0   # -12%
        assert tp == 120.0  # +20%

    def test_atr_tighter(self):
        # ATR stop = 100 - 3*2 = 94, fixed = 95. ATR is lower → use fixed (higher=tighter)
        sl, tp = self.calc.calc_initial("momentum", 100.0, atr=3.0)
        assert sl == 95.0  # fixed is tighter

    def test_atr_wider(self):
        # ATR stop = 100 - 1*2 = 98, fixed = 95. ATR is higher → use ATR (tighter)
        sl, tp = self.calc.calc_initial("momentum", 100.0, atr=1.0)
        assert sl == 98.0

    def test_stop_loss_triggered(self):
        hit, reason = self.calc.check_exit(
            "momentum", 100.0, date(2026, 3, 1), 94.0, 100.0, date(2026, 3, 5), 95.0
        )
        assert hit is True
        assert reason == "stop_loss"

    def test_trailing_stop(self):
        # Max price 120 (20% gain), trailing at 4%. Stop = 120 * 0.96 = 115.2
        hit, reason = self.calc.check_exit(
            "value", 100.0, date(2026, 3, 1), 115.0, 120.0, date(2026, 3, 10), 88.0
        )
        assert hit is True
        assert reason == "trailing_stop"

    def test_time_limit(self):
        hit, reason = self.calc.check_exit(
            "momentum", 100.0, date(2026, 3, 1), 102.0, 102.0, date(2026, 3, 15), 95.0
        )
        assert hit is True
        assert reason == "time_limit"  # 14 days > 10

    def test_no_exit(self):
        hit, reason = self.calc.check_exit(
            "value", 100.0, date(2026, 3, 1), 105.0, 105.0, date(2026, 3, 5), 88.0
        )
        assert hit is False
        assert reason == ""


# ============================================================
# Drawdown Monitor Tests
# ============================================================
class TestDrawdownMonitor:
    def test_normal(self):
        dm = DrawdownMonitor(1_000_000)
        level = dm.update(980_000)
        assert level == DrawdownLevel.NORMAL
        assert dm.allows_new_positions() is True

    def test_yellow(self):
        dm = DrawdownMonitor(1_000_000)
        level = dm.update(910_000)  # 9% drawdown
        assert level == DrawdownLevel.YELLOW
        assert dm.allows_new_positions() is False
        assert dm.get_position_limit_override() is None  # yellow doesn't force reduce

    def test_orange(self):
        dm = DrawdownMonitor(1_000_000)
        level = dm.update(870_000)  # 13% drawdown
        assert level == DrawdownLevel.ORANGE
        assert dm.get_position_limit_override() == 0.50

    def test_red(self):
        dm = DrawdownMonitor(1_000_000)
        level = dm.update(830_000)  # 17% drawdown
        assert level == DrawdownLevel.RED
        assert dm.get_position_limit_override() == 0.20

    def test_circuit_break(self):
        dm = DrawdownMonitor(1_000_000)
        level = dm.update(810_000)  # 19% drawdown
        assert level == DrawdownLevel.CIRCUIT_BREAK
        assert dm.get_position_limit_override() == 0.0

    def test_high_water_mark_update(self):
        dm = DrawdownMonitor(1_000_000)
        dm.update(1_100_000)  # new high
        assert dm.high_water_mark == 1_100_000
        level = dm.update(1_000_000)  # 9% from peak
        assert level == DrawdownLevel.YELLOW


# ============================================================
# Position Sizer Tests
# ============================================================
class TestPositionSizer:
    def _make_signal(self, code="000001", price=10.0, confidence=0.7,
                     direction=0.8, strategy="value"):
        return Signal(
            trade_date=date(2026, 3, 27), stock_code=code, strategy=strategy,
            direction=direction, confidence=confidence, holding_period=60,
            entry_price=price, stop_loss=price*0.88, take_profit=price*1.2,
            factors={},
        )

    def test_basic_sizing(self):
        sizer = PositionSizer(1_000_000)
        signals = [self._make_signal()]
        # Simple portfolio mock
        portfolio = _MockPortfolio(0.0, 1_000_000)
        orders = sizer.size(signals, MarketState.NEUTRAL_LOW, portfolio)
        assert len(orders) == 1
        assert orders[0].shares > 0
        assert orders[0].shares % 100 == 0

    def test_lot_rounding(self):
        # High price stock: 100万 * 7% / 2000 = 35 shares → round to 0 lots
        sizer = PositionSizer(1_000_000)
        sig = self._make_signal(price=2000.0, confidence=0.7)
        portfolio = _MockPortfolio(0.0, 1_000_000)
        orders = sizer.size([sig], MarketState.NEUTRAL_LOW, portfolio)
        if orders:
            assert orders[0].shares % 100 == 0

    def test_no_capacity(self):
        sizer = PositionSizer(1_000_000)
        signals = [self._make_signal()]
        portfolio = _MockPortfolio(0.95, 1_000_000)  # 95% invested
        orders = sizer.size(signals, MarketState.NEUTRAL_LOW, portfolio)
        assert len(orders) == 0

    def test_empty_signals(self):
        sizer = PositionSizer(1_000_000)
        portfolio = _MockPortfolio(0.0, 1_000_000)
        orders = sizer.size([], MarketState.BULL_LOW, portfolio)
        assert orders == []


class _MockPortfolio:
    def __init__(self, position_pct: float, total_value: float):
        self._pct = position_pct
        self._total = total_value

    def get_total_position_pct(self):
        return self._pct

    def get_total_value_estimate(self):
        return self._total
