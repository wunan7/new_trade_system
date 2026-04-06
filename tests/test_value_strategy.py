from datetime import date
import pandas as pd
import numpy as np
from trading_system.strategies.value import ValueStrategy
from trading_system.strategies.base import Signal

def test_value_strategy_filters():
    """Stock passing all filters gets signal, failing stock excluded."""
    factor_df = pd.DataFrame({
        "pb": [2.0, 8.0, 3.0],  # percentiles: 0%, 100%, 50%
        "roe": [15.0, 5.0, 20.0],  # pass, fail, pass
        "dividend_yield": [0.03, 0.01, 0.025],  # pass, fail, pass
        "debt_ratio": [50.0, 70.0, 55.0],  # pass, fail, pass
        "ocf_to_profit": [1.2, 1.5, 1.0],
        "goodwill_ratio": [0.05, 0.15, 0.08],
        "accrual_ratio": [-0.01, 0.02, -0.005],
    }, index=["A", "B", "C"])

    strategy = ValueStrategy()
    signals = strategy.generate(date(2026, 3, 27), factor_df)

    # Stock A: passes all filters
    # Stock B: fails roe, dividend_yield, debt_ratio
    # Stock C: passes all filters
    codes = [s.stock_code for s in signals]
    assert "A" in codes
    assert "B" not in codes
    assert "C" in codes

def test_value_strategy_scoring():
    """Higher score → higher direction."""
    factor_df = pd.DataFrame({
        "pb": [1.0, 5.0],  # A has lower pb (better)
        "roe": [25.0, 15.0],  # A has higher roe
        "dividend_yield": [0.04, 0.02],  # A has higher yield
        "debt_ratio": [30.0, 50.0],
        "ocf_to_profit": [2.0, 1.0],  # A has higher ocf
        "goodwill_ratio": [0.05, 0.05],
        "accrual_ratio": [-0.01, -0.01],
    }, index=["A", "B"])

    strategy = ValueStrategy()
    signals = strategy.generate(date(2026, 3, 27), factor_df)

    sig_a = [s for s in signals if s.stock_code == "A"][0]
    sig_b = [s for s in signals if s.stock_code == "B"][0]
    assert sig_a.direction > sig_b.direction

def test_value_strategy_confidence_boost():
    """Low goodwill + negative accrual → confidence boost."""
    factor_df = pd.DataFrame({
        "pb": [2.0],
        "roe": [20.0],
        "dividend_yield": [0.03],
        "debt_ratio": [40.0],
        "ocf_to_profit": [1.5],
        "goodwill_ratio": [0.05],  # < 0.1 → +0.1
        "accrual_ratio": [-0.02],  # < 0 → +0.1
    }, index=["A"])

    strategy = ValueStrategy()
    signals = strategy.generate(date(2026, 3, 27), factor_df)

    assert signals[0].confidence >= 0.7  # base 0.5 + 0.1 + 0.1

def test_value_strategy_top_n():
    """Returns at most 20 stocks."""
    # Create 30 stocks all passing filters
    factor_df = pd.DataFrame({
        "pb": np.random.uniform(1, 3, 30),
        "roe": np.random.uniform(15, 25, 30),
        "dividend_yield": np.random.uniform(0.025, 0.04, 30),
        "debt_ratio": np.random.uniform(30, 55, 30),
        "ocf_to_profit": np.random.uniform(1.0, 2.0, 30),
        "goodwill_ratio": np.random.uniform(0, 0.1, 30),
        "accrual_ratio": np.random.uniform(-0.02, 0.01, 30),
    }, index=[f"S{i:03d}" for i in range(30)])

    strategy = ValueStrategy()
    signals = strategy.generate(date(2026, 3, 27), factor_df)

    assert len(signals) <= 20
