"""Tests for technical factor functions."""
import numpy as np
import pandas as pd
import pytest
from trading_system.factors.technical import (
    momentum_nd, volatility_nd, atr_14d, volume_ratio_5d, turnover_deviation,
    macd_signal, adx_14d, bb_width, rs_vs_index, obv_slope,
)


class TestMomentum:
    def test_constant_growth(self):
        """A series growing 1% per day should have 5d momentum ≈ 5.1%."""
        n = 30
        close = pd.Series(100 * (1.01 ** np.arange(n)), dtype=float)
        mom5 = momentum_nd(close, 5)
        # (1.01^5) - 1 ≈ 0.05101
        expected = 1.01**5 - 1
        assert abs(mom5.iloc[-1] - expected) < 0.001

    def test_flat_price_zero_momentum(self):
        """Constant price should give zero momentum."""
        close = pd.Series([100.0] * 20)
        mom5 = momentum_nd(close, 5)
        assert mom5.iloc[-1] == 0.0

    def test_nan_warmup(self):
        """First n values should be NaN."""
        close = pd.Series(range(1, 21), dtype=float)
        mom5 = momentum_nd(close, 5)
        assert mom5.iloc[:5].isna().all()
        assert mom5.iloc[5:].notna().all()


class TestVolatility:
    def test_constant_price_zero_vol(self):
        """Constant price should have zero volatility."""
        close = pd.Series([100.0] * 30)
        vol = volatility_nd(close, 20)
        # After warmup, values should be 0
        valid = vol.dropna()
        assert (valid == 0).all()

    def test_positive_vol_for_varying_price(self):
        """Varying prices should produce positive volatility."""
        np.random.seed(42)
        close = pd.Series(100 + np.cumsum(np.random.randn(50)))
        vol = volatility_nd(close, 20)
        valid = vol.dropna()
        assert (valid > 0).all()


class TestATR:
    def test_returns_series(self):
        """ATR should return a Series of correct length."""
        n = 30
        high = pd.Series(np.random.uniform(101, 105, n))
        low = pd.Series(np.random.uniform(95, 99, n))
        close = pd.Series(np.random.uniform(98, 103, n))
        result = atr_14d(high, low, close)
        assert isinstance(result, pd.Series)
        assert len(result) == n

    def test_atr_positive(self):
        """ATR should be non-negative."""
        n = 30
        close = pd.Series(100 + np.cumsum(np.random.randn(n)))
        high = close + np.abs(np.random.randn(n))
        low = close - np.abs(np.random.randn(n))
        result = atr_14d(high, low, close)
        valid = result.dropna()
        assert (valid >= 0).all()


class TestVolumeRatio:
    def test_uniform_volume_ratio_one(self):
        """Constant volume should give ratio = 1.0."""
        volume = pd.Series([1_000_000] * 20, dtype=float)
        ratio = volume_ratio_5d(volume)
        valid = ratio.dropna()
        assert np.allclose(valid, 1.0)

    def test_spike_detected(self):
        """A volume spike should produce ratio > 1."""
        volume = pd.Series([1_000_000] * 10 + [5_000_000], dtype=float)
        ratio = volume_ratio_5d(volume)
        assert ratio.iloc[-1] > 1.0


class TestTurnoverDeviation:
    def test_constant_turnover_zero_dev(self):
        """Constant turnover should give deviation = 0 (or NaN if std=0)."""
        turnover = pd.Series([3.0] * 30)
        dev = turnover_deviation(turnover)
        # std is 0, so result should be NaN (we replace 0 std with NaN)
        valid = dev.iloc[20:]  # after warmup
        assert valid.isna().all()

    def test_high_turnover_positive_dev(self):
        """Above-average turnover should produce positive deviation."""
        turnover = pd.Series([2.0] * 25 + [10.0])
        dev = turnover_deviation(turnover)
        assert dev.iloc[-1] > 0


class TestMacdSignal:
    def test_returns_series(self):
        np.random.seed(42)
        close = pd.Series(100 + np.cumsum(np.random.randn(50)))
        result = macd_signal(close)
        assert isinstance(result, pd.Series)
        assert len(result) == 50


class TestAdx:
    def test_in_range(self):
        np.random.seed(42)
        n = 50
        close = pd.Series(100 + np.cumsum(np.random.randn(n)))
        high = close + np.abs(np.random.randn(n))
        low = close - np.abs(np.random.randn(n))
        result = adx_14d(high, low, close)
        valid = result.dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()


class TestBBWidth:
    def test_positive_for_varying_price(self):
        np.random.seed(42)
        close = pd.Series(100 + np.cumsum(np.random.randn(50)))
        result = bb_width(close)
        valid = result.dropna()
        assert (valid > 0).all()


class TestRsVsIndex:
    def test_same_series_zero_rs(self):
        """When stock = index, relative strength should be 0."""
        close = pd.Series(range(1, 31), dtype=float)
        result = rs_vs_index(close, close, n=5)
        valid = result.dropna()
        assert np.allclose(valid, 0.0, atol=1e-10)

    def test_outperformance(self):
        """Stock with higher return should have positive RS."""
        stock = pd.Series(100 * (1.02 ** np.arange(30)), dtype=float)
        index = pd.Series(100 * (1.01 ** np.arange(30)), dtype=float)
        result = rs_vs_index(stock, index, n=5)
        valid = result.dropna()
        assert (valid > 0).all()


class TestObvSlope:
    def test_uptrend_positive_slope(self):
        """Consistent uptrend should produce positive OBV slope."""
        n = 40
        close = pd.Series(100 + np.arange(n) * 0.5, dtype=float)
        volume = pd.Series([1_000_000] * n, dtype=float)
        result = obv_slope(close, volume, n=20)
        valid = result.dropna()
        assert len(valid) > 0
        assert valid.iloc[-1] > 0

    def test_returns_series(self):
        n = 30
        close = pd.Series(np.random.randn(n).cumsum() + 100)
        volume = pd.Series(np.random.randint(100000, 1000000, n), dtype=float)
        result = obv_slope(close, volume, n=20)
        assert isinstance(result, pd.Series)
        assert len(result) == n
