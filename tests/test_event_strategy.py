from datetime import date

from trading_system.strategies.event_driven import EventDrivenStrategy


def test_low_amount_low_impact_buyback_is_filtered(monkeypatch):
    strategy = EventDrivenStrategy(db_engine=None)

    monkeypatch.setattr(
        strategy,
        "_query_events",
        lambda event_type, trade_date: [
            ("000001", trade_date, "回购预案", "回购金额: 1000万元", 0.2, "low")
        ],
    )

    signals = strategy._handle_buyback(date(2026, 5, 5))

    assert signals == []


def test_high_beat_earnings_signal_passes(monkeypatch):
    strategy = EventDrivenStrategy(db_engine=None)

    monkeypatch.setattr(
        strategy,
        "_query_events",
        lambda event_type, trade_date: [
            ("600519", trade_date, "业绩超预期", "变动幅度: +600.0%", 0.8, "high")
        ],
    )

    signals = strategy._handle_earnings_beat(date(2026, 5, 5))

    assert len(signals) == 1
    assert signals[0].stock_code == "600519"
    assert signals[0].strategy == "event"
