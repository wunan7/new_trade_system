from datetime import date
from trading_system.strategies.base import Signal
from trading_system.signals.writer import write_signals
from trading_system.db.models import SignalHistory
from trading_system.db.engine import get_engine, session_scope
from sqlalchemy import text

def test_write_signals_inserts():
    """Insert signals and verify count."""
    signals = [
        Signal(
            trade_date=date(2000, 1, 1),
            stock_code="TEST01",
            strategy="value",
            direction=0.8,
            confidence=0.6,
            holding_period=60,
            entry_price=100.0,
            stop_loss=95.0,
            take_profit=110.0,
            factors={"roe": 15.0}
        ),
        Signal(
            trade_date=date(2000, 1, 1),
            stock_code="TEST02",
            strategy="growth",
            direction=0.7,
            confidence=0.5,
            holding_period=60,
            entry_price=50.0,
            stop_loss=48.0,
            take_profit=55.0,
            factors={"profit_growth": 50.0}
        ),
    ]

    with session_scope() as session:
        count = write_signals(session, signals)
        assert count == 2

def test_write_signals_empty():
    """Empty list returns 0."""
    with session_scope() as session:
        count = write_signals(session, [])
        assert count == 0

def test_write_signals_batch():
    """Multiple batches all written."""
    signals = [
        Signal(
            trade_date=date(2000, 1, 2),
            stock_code=f"BATCH{i:02d}",
            strategy="momentum",
            direction=0.5,
            confidence=0.5,
            holding_period=10,
            entry_price=100.0,
            stop_loss=95.0,
            take_profit=105.0,
            factors={}
        )
        for i in range(5)
    ]

    with session_scope() as session:
        count = write_signals(session, signals, batch_size=2)
        assert count == 5
