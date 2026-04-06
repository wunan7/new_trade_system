"""Tests for MarketStateDetector."""
from datetime import date
import pandas as pd
import numpy as np
import pytest
from trading_system.strategies.market_state import MarketStateDetector
from trading_system.strategies.base import MarketState


def _make_index_df(n_days: int, trend: str, high_vol: bool) -> pd.DataFrame:
    """Build a deterministic synthetic CSI300 close series.

    trend: "bull"    → close > MA60*1.02 and 20d momentum > 0
           "bear"    → close < MA60*0.98 and 20d momentum < 0
           "neutral" → neither threshold crossed
    high_vol: True   → annualised 20d vol > annualised 60d vol * 1.2
              False  → consistent low vol throughout
    """
    dates = pd.date_range("2025-01-02", periods=n_days, freq="B")

    # ---- deterministic daily return (no randomness) ------------------
    # We use a tiny alternating oscillation so vol is non-zero but small,
    # and layer a pure drift on top to control trend.
    if trend == "bull":
        drift = 0.004          # +0.4 %/day → clear uptrend
    elif trend == "bear":
        drift = -0.004         # -0.4 %/day → clear downtrend
    else:
        drift = 0.0            # flat

    # Low-vol base noise: alternating ±0.003 (ann ~4.7%)
    base_noise = np.where(np.arange(n_days) % 2 == 0, 0.003, -0.003)

    if high_vol:
        # Replace the last 20 returns with alternating ±0.03 (ann ~47%)
        # This makes vol_20d ≈ 47% >> vol_60d ≈ 12-15%
        base_noise = base_noise.copy()
        base_noise[-20:] = np.where(np.arange(20) % 2 == 0, 0.03, -0.03)

    daily_returns = drift + base_noise
    price = 3900.0 * np.cumprod(1 + daily_returns)

    df = pd.DataFrame({"close": price}, index=dates)
    df.index.name = "trade_date"
    return df


class TestDetectLogic:
    """Unit tests using a mock loader so no DB connection is needed."""

    def _detector_with_mock(self, index_df: pd.DataFrame) -> "MarketStateDetector":
        """Return a detector whose internal loader returns index_df."""
        detector = MarketStateDetector.__new__(MarketStateDetector)

        class _MockLoader:
            def load_index_prices(self, trade_date, index_code="000300"):
                return index_df

        detector.loader = _MockLoader()
        return detector

    def test_detect_bull_low(self):
        """Uptrend + low volatility → BULL_LOW."""
        df = _make_index_df(n_days=80, trend="bull", high_vol=False)
        detector = self._detector_with_mock(df)
        state = detector.detect(date(2025, 6, 1))
        assert state == MarketState.BULL_LOW

    def test_detect_bull_high(self):
        """Uptrend + high volatility → BULL_HIGH."""
        df = _make_index_df(n_days=80, trend="bull", high_vol=True)
        detector = self._detector_with_mock(df)
        state = detector.detect(date(2025, 6, 1))
        assert state == MarketState.BULL_HIGH

    def test_detect_bear_high(self):
        """Downtrend + high volatility → BEAR_HIGH."""
        df = _make_index_df(n_days=80, trend="bear", high_vol=True)
        detector = self._detector_with_mock(df)
        state = detector.detect(date(2025, 6, 1))
        assert state == MarketState.BEAR_HIGH

    def test_detect_bear_low(self):
        """Downtrend + low volatility → BEAR_LOW."""
        df = _make_index_df(n_days=80, trend="bear", high_vol=False)
        detector = self._detector_with_mock(df)
        state = detector.detect(date(2025, 6, 1))
        assert state == MarketState.BEAR_LOW

    def test_detect_insufficient_data_returns_neutral_low(self):
        """When fewer than 60 rows are available, default to NEUTRAL_LOW."""
        df = _make_index_df(n_days=30, trend="bull", high_vol=False)
        detector = self._detector_with_mock(df)
        state = detector.detect(date(2025, 2, 1))
        assert state == MarketState.NEUTRAL_LOW


class TestGetWeights:
    def test_get_weights_bull_low(self):
        """get_weights returns correct dict for BULL_LOW."""
        detector = MarketStateDetector.__new__(MarketStateDetector)
        weights = detector.get_weights(MarketState.BULL_LOW)
        assert weights["value"] == 0.20
        assert weights["growth"] == 0.35
        assert weights["position_limit"] == 0.90

    def test_get_weights_bear_high(self):
        """get_weights returns correct dict for BEAR_HIGH."""
        detector = MarketStateDetector.__new__(MarketStateDetector)
        weights = detector.get_weights(MarketState.BEAR_HIGH)
        assert weights["value"] == 0.30
        assert weights["growth"] == 0.00
        assert weights["position_limit"] == 0.20


class TestGetPositionLimit:
    def test_bear_high_limit(self):
        """get_position_limit returns 0.20 for BEAR_HIGH."""
        detector = MarketStateDetector.__new__(MarketStateDetector)
        limit = detector.get_position_limit(MarketState.BEAR_HIGH)
        assert limit == 0.20

    def test_bull_low_limit(self):
        """get_position_limit returns 0.90 for BULL_LOW."""
        detector = MarketStateDetector.__new__(MarketStateDetector)
        limit = detector.get_position_limit(MarketState.BULL_LOW)
        assert limit == 0.90


class TestLiveDB:
    """Integration test against the real PostgreSQL finance DB."""

    @pytest.mark.integration
    def test_detect_with_live_db(self):
        """Test detection with real CSI300 data — result is market-dependent."""
        from trading_system.db.engine import get_engine
        detector = MarketStateDetector(get_engine())
        state = detector.detect(date(2026, 3, 27))
        assert isinstance(state, MarketState)
