from datetime import date
from trading_system.strategies.base import Signal, MarketState, STRATEGY_WEIGHTS, BaseStrategy

def test_signal_dataclass():
    """Signal dataclass has all required fields."""
    sig = Signal(
        trade_date=date(2026, 3, 27),
        stock_code="600519",
        strategy="value",
        direction=0.8,
        confidence=0.6,
        holding_period=60,
        entry_price=1800.0,
        stop_loss=1700.0,
        take_profit=2000.0,
        factors={"roe": 25.0, "pb": 6.9}
    )
    assert sig.stock_code == "600519"
    assert sig.direction == 0.8

def test_market_state_enum():
    """MarketState enum has 6 states."""
    states = list(MarketState)
    assert len(states) == 6
    assert MarketState.BULL_LOW in states
    assert MarketState.BEAR_HIGH in states

def test_strategy_weights():
    """STRATEGY_WEIGHTS has entries for all 6 states."""
    assert len(STRATEGY_WEIGHTS) == 6
    for state in MarketState:
        assert state in STRATEGY_WEIGHTS
        weights = STRATEGY_WEIGHTS[state]
        assert "value" in weights
        assert "growth" in weights
        assert "momentum" in weights
        assert "position_limit" in weights

def test_base_strategy_abstract():
    """BaseStrategy cannot be instantiated (abstract)."""
    import pytest
    with pytest.raises(TypeError):
        BaseStrategy()
