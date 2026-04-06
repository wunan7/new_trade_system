from datetime import date
import pandas as pd
import numpy as np
from trading_system.strategies.growth import GrowthStrategy

def test_growth_strategy_filters():
    """Stock passing all filters gets signal, failing stock excluded."""
    factor_df = pd.DataFrame({
        "profit_growth": [50.0, 20.0, 35.0],  # pass, fail, pass
        "revenue_growth": [30.0, 15.0, 25.0],  # pass, fail, pass
        "roe": [12.0, 5.0, 10.0],  # pass, fail, pass
        "net_margin": [18.0, 10.0, 12.0],
        "gross_margin": [40.0, 30.0, 35.0],
    }, index=["A", "B", "C"])

    strategy = GrowthStrategy()
    signals = strategy.generate(date(2026, 3, 27), factor_df)

    codes = [s.stock_code for s in signals]
    assert "A" in codes
    assert "B" not in codes
    assert "C" in codes

def test_growth_strategy_scoring():
    """Higher growth → higher direction."""
    factor_df = pd.DataFrame({
        "profit_growth": [100.0, 40.0],  # A has higher
        "revenue_growth": [50.0, 25.0],  # A has higher
        "roe": [20.0, 15.0],
        "net_margin": [15.0, 12.0],
        "gross_margin": [50.0, 40.0],
    }, index=["A", "B"])

    strategy = GrowthStrategy()
    signals = strategy.generate(date(2026, 3, 27), factor_df)

    sig_a = [s for s in signals if s.stock_code == "A"][0]
    sig_b = [s for s in signals if s.stock_code == "B"][0]
    assert sig_a.direction > sig_b.direction

def test_growth_strategy_confidence_boost():
    """High net_margin + high revenue_growth → confidence boost."""
    factor_df = pd.DataFrame({
        "profit_growth": [50.0],
        "revenue_growth": [45.0],  # > 40 → +0.1
        "roe": [15.0],
        "net_margin": [18.0],  # > 15 → +0.1
        "gross_margin": [50.0],
    }, index=["A"])

    strategy = GrowthStrategy()
    signals = strategy.generate(date(2026, 3, 27), factor_df)

    assert signals[0].confidence >= 0.7  # base 0.5 + 0.1 + 0.1

def test_growth_strategy_top_n():
    """Returns at most 20 stocks."""
    factor_df = pd.DataFrame({
        "profit_growth": np.random.uniform(35, 100, 30),
        "revenue_growth": np.random.uniform(25, 60, 30),
        "roe": np.random.uniform(10, 25, 30),
        "net_margin": np.random.uniform(10, 20, 30),
        "gross_margin": np.random.uniform(30, 60, 30),
    }, index=[f"S{i:03d}" for i in range(30)])

    strategy = GrowthStrategy()
    signals = strategy.generate(date(2026, 3, 27), factor_df)

    assert len(signals) <= 20
