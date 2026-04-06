import pytest
import pandas as pd
import numpy as np
from datetime import date, timedelta

@pytest.fixture
def synthetic_ohlcv():
    """100-row OHLCV DataFrame for a single stock with uptrend."""
    n = 100
    dates = [date(2025, 1, 2) + timedelta(days=i) for i in range(n)]
    np.random.seed(42)
    base = 100
    returns = np.random.normal(0.001, 0.02, n)
    close = base * np.cumprod(1 + returns)
    high = close * (1 + np.abs(np.random.normal(0, 0.01, n)))
    low = close * (1 - np.abs(np.random.normal(0, 0.01, n)))
    open_ = close * (1 + np.random.normal(0, 0.005, n))
    volume = np.random.randint(1_000_000, 10_000_000, n)

    df = pd.DataFrame({
        "trade_date": dates,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "amount": close * volume,
        "pct_change": np.concatenate([[0], np.diff(close) / close[:-1] * 100]),
        "turnover": np.random.uniform(1, 5, n),
    })
    df.set_index("trade_date", inplace=True)
    return df

@pytest.fixture
def synthetic_summary():
    """Financial summary DataFrame indexed by stock code."""
    return pd.DataFrame({
        "code": ["000001", "000002", "600519"],
        "report_date": [date(2025, 12, 31)] * 3,
        "roe": [12.5, 8.3, 25.1],
        "gross_margin": [35.2, 22.1, 91.5],
        "net_margin": [18.5, 10.2, 52.3],
        "debt_to_assets": [88.5, 65.3, 18.2],
        "revenue_growth": [5.2, -3.1, 15.8],
        "earnings_growth": [8.1, -12.5, 20.3],
    }).set_index("code")
