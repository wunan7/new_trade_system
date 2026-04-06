"""Tests for signal generator orchestrator."""
from datetime import date
from unittest.mock import Mock, patch
import pandas as pd
from trading_system.signals.generator import SignalGenerator
from trading_system.strategies.base import Signal, MarketState


def test_signal_generator_aggregation():
    """Test signal aggregation when same stock appears in multiple strategies."""
    generator = SignalGenerator()

    # Mock signals from different strategies for same stock
    signals = [
        Signal(
            trade_date=date(2026, 3, 27),
            stock_code="600519",
            strategy="value",
            direction=1.0,
            confidence=0.8,
            holding_period=30,
            entry_price=0.0,
            stop_loss=0.0,
            take_profit=0.0,
            factors={"pb": 10.0, "roe": 25.0}
        ),
        Signal(
            trade_date=date(2026, 3, 27),
            stock_code="600519",
            strategy="growth",
            direction=1.0,
            confidence=0.7,
            holding_period=20,
            entry_price=0.0,
            stop_loss=0.0,
            take_profit=0.0,
            factors={"profit_growth": 30.0}
        ),
    ]

    # Aggregate with neutral_low market state
    aggregated = generator._aggregate_signals(signals, MarketState.NEUTRAL_LOW)

    assert len(aggregated) == 1
    assert aggregated[0].stock_code == "600519"
    assert aggregated[0].strategy == "multi"
    assert aggregated[0].holding_period == 30  # max of 30 and 20
    assert "pb" in aggregated[0].factors
    assert "profit_growth" in aggregated[0].factors


def test_signal_generator_run_integration():
    """Integration test with mocked data loading."""
    generator = SignalGenerator()

    test_date = date(2026, 3, 27)

    # Mock factor data
    factor_df = pd.DataFrame({
        "momentum_20d": [0.15, 0.12],
        "momentum_60d": [0.10, 0.09],
        "volume_ratio_5d": [1.2, 1.0],
        "adx": [30.0, 28.0],
        "obv_slope": [100.0, 50.0],
        "roe": [20.0, 15.0],
        "gross_margin": [40.0, 35.0],
        "net_margin": [15.0, 12.0],
        "debt_ratio": [40.0, 50.0],
        "revenue_growth": [30.0, 25.0],
        "profit_growth": [50.0, 35.0],
        "ocf_to_profit": [1.5, 1.2],
        "accrual_ratio": [-0.01, 0.0],
        "goodwill_ratio": [0.05, 0.08],
        "pb": [2.0, 3.0],
        "dividend_yield": [0.03, 0.025],
    }, index=["600519", "000858"])

    # Mock the data loading and writing
    with patch.object(generator, '_load_factor_df', return_value=factor_df):
        with patch('trading_system.signals.generator.write_signals', return_value=2) as mock_write:
            count = generator.run(test_date)

            assert count == 2
            assert mock_write.called
