from sqlalchemy import create_engine, inspect
from trading_system.db.base import Base
from trading_system.db.models import SignalHistory


def test_signal_history_columns():
    """Verify SignalHistory has all required columns."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    columns = {c["name"] for c in inspector.get_columns("signal_history")}

    expected = {
        "id", "trade_date", "stock_code", "strategy",
        "direction", "confidence", "holding_period",
        "entry_price", "stop_loss", "take_profit",
        "factors_json", "was_executed", "filter_reason",
        "llm_override", "created_at"
    }
    assert expected.issubset(columns), f"Missing: {expected - columns}"


def test_signal_history_indexes():
    """Verify indexes on (stock_code, trade_date) and (strategy, trade_date)."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    indexes = inspector.get_indexes("signal_history")
    index_cols = [tuple(idx["column_names"]) for idx in indexes]
    assert ("stock_code", "trade_date") in index_cols
    assert ("strategy", "trade_date") in index_cols
