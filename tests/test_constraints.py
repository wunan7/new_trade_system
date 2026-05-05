from datetime import date

from trading_system.risk.constraints import ConstraintFilter
from trading_system.strategies.base import Signal


class TestConstraintFilterCooldown:
    def _make_signal(self, code="000001"):
        return Signal(
            trade_date=date(2026, 3, 27),
            stock_code=code,
            strategy="value",
            direction=0.8,
            confidence=0.7,
            holding_period=60,
            entry_price=10.0,
            stop_loss=8.8,
            take_profit=12.0,
            factors={},
        )

    def test_recently_sold_1_trading_day_ago_is_rejected(self, monkeypatch):
        constraint_filter = ConstraintFilter(engine=None)
        signal = self._make_signal()

        monkeypatch.setattr(
            constraint_filter,
            "_load_trade_constraints",
            lambda trade_date, codes: {},
        )
        monkeypatch.setattr(
            constraint_filter,
            "_load_listing_info",
            lambda codes, trade_date: {"000001": {"days_listed": 999, "industry": "Bank"}},
        )
        monkeypatch.setattr(
            constraint_filter,
            "_load_liquidity",
            lambda trade_date, codes: {"000001": 10_000_000},
        )
        monkeypatch.setattr(
            constraint_filter,
            "_load_recent_sell_info",
            lambda trade_date, codes: {"000001": 1},
            raising=False,
        )

        passed, rejected = constraint_filter.filter([signal], date(2026, 3, 27))

        assert passed == []
        assert len(rejected) == 1
        assert rejected[0][0] == signal
        assert rejected[0][1] == "cooldown(1d)"

    def test_sold_6_trading_days_ago_is_allowed(self, monkeypatch):
        constraint_filter = ConstraintFilter(engine=None)
        signal = self._make_signal()

        monkeypatch.setattr(
            constraint_filter,
            "_load_trade_constraints",
            lambda trade_date, codes: {},
        )
        monkeypatch.setattr(
            constraint_filter,
            "_load_listing_info",
            lambda codes, trade_date: {"000001": {"days_listed": 999, "industry": "Bank"}},
        )
        monkeypatch.setattr(
            constraint_filter,
            "_load_liquidity",
            lambda trade_date, codes: {"000001": 10_000_000},
        )
        monkeypatch.setattr(
            constraint_filter,
            "_load_recent_sell_info",
            lambda trade_date, codes: {"000001": 3},
            raising=False,
        )

        passed, rejected = constraint_filter.filter([signal], date(2026, 3, 27))

        assert passed == [signal]
        assert rejected == []
