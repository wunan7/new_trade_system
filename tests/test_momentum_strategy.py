from datetime import date
import pandas as pd
import numpy as np
from trading_system.strategies.momentum import MomentumStrategy

def test_momentum_strategy_filters():
    """Stock passing all filters gets signal, failing stock excluded."""
    factor_df = pd.DataFrame({
        "momentum_20d": [0.15, 0.02, 0.12, 0.60],  # A/C pass, B fails pct, D overheated
        "momentum_60d": [0.10, 0.08, 0.09, 0.11],
        "volume_ratio_5d": [1.2, 0.3, 1.0, 1.5],  # A/C/D pass, B fails
        "adx": [30.0, 25.0, 28.0, 35.0],
        "obv_slope": [100.0, -50.0, 200.0, 150.0],
    }, index=["A", "B", "C", "D"])

    strategy = MomentumStrategy()
    signals = strategy.generate(date(2026, 3, 27), factor_df)

    codes = [s.stock_code for s in signals]
    assert "A" in codes
    assert "B" not in codes  # low momentum_20d percentile + low volume
    assert "C" in codes
    assert "D" not in codes  # overheated (momentum_20d > 0.5)

def test_momentum_strategy_scoring():
    """Higher momentum → higher direction."""
    factor_df = pd.DataFrame({
        "momentum_20d": [0.20, 0.10],  # A higher
        "momentum_60d": [0.15, 0.08],  # A higher
        "volume_ratio_5d": [1.5, 1.0],
        "adx": [35.0, 25.0],
        "obv_slope": [100.0, 50.0],
    }, index=["A", "B"])

    strategy = MomentumStrategy()
    signals = strategy.generate(date(2026, 3, 27), factor_df)

    sig_a = [s for s in signals if s.stock_code == "A"][0]
    sig_b = [s for s in signals if s.stock_code == "B"][0]
    assert sig_a.direction > sig_b.direction

def test_momentum_strategy_confidence_obv():
    """Positive OBV slope → confidence boost, negative → penalty."""
    factor_df = pd.DataFrame({
        "momentum_20d": [0.15, 0.12],
        "momentum_60d": [0.10, 0.09],
        "volume_ratio_5d": [1.2, 1.0],
        "adx": [30.0, 28.0],
        "obv_slope": [100.0, -50.0],  # A positive, B negative
    }, index=["A", "B"])

    strategy = MomentumStrategy()
    signals = strategy.generate(date(2026, 3, 27), factor_df)

    sig_a = [s for s in signals if s.stock_code == "A"][0]
    sig_b = [s for s in signals if s.stock_code == "B"][0]
    assert sig_a.confidence == 0.6  # base 0.5 + 0.1
    assert sig_b.confidence == 0.4  # base 0.5 - 0.1

def test_momentum_strategy_top_n():
    """Returns at most 15 stocks."""
    factor_df = pd.DataFrame({
        "momentum_20d": np.random.uniform(0.10, 0.30, 25),
        "momentum_60d": np.random.uniform(0.08, 0.15, 25),
        "volume_ratio_5d": np.random.uniform(0.8, 2.0, 25),
        "adx": np.random.uniform(20, 40, 25),
        "obv_slope": np.random.uniform(-100, 200, 25),
    }, index=[f"S{i:03d}" for i in range(25)])

    strategy = MomentumStrategy()
    signals = strategy.generate(date(2026, 3, 27), factor_df)

    assert len(signals) <= 15
