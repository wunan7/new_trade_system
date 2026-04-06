import numpy as np
import pandas as pd
import pytest
from trading_system.pipeline.standardizer import winsorize_mad, zscore_standardize, standardize_factors


class TestWinsorizeMad:
    def test_clips_extreme_outlier(self):
        """An outlier at 100x the median should be clipped."""
        s = pd.Series([1, 2, 3, 4, 5, 500])
        result = winsorize_mad(s)
        assert result.max() < 500
        assert result.max() < 20  # Should be clipped to within ~3 MAD

    def test_preserves_normal_values(self):
        """Values within 3 MAD should not change."""
        s = pd.Series([10, 11, 12, 13, 14])
        result = winsorize_mad(s)
        pd.testing.assert_series_equal(result, s)

    def test_nan_passthrough(self):
        """NaN values should remain NaN."""
        s = pd.Series([1, 2, np.nan, 4, 5])
        result = winsorize_mad(s)
        assert np.isnan(result.iloc[2])

    def test_all_nan_returns_all_nan(self):
        """All-NaN series should return all-NaN."""
        s = pd.Series([np.nan, np.nan, np.nan])
        result = winsorize_mad(s)
        assert result.isna().all()

    def test_constant_series(self):
        """Constant series (MAD=0) should be returned unchanged."""
        s = pd.Series([5.0, 5.0, 5.0, 5.0])
        result = winsorize_mad(s)
        pd.testing.assert_series_equal(result, s)


class TestZscoreStandardize:
    def test_normal_data_mean_std(self):
        """Z-scored normal data should have mean≈0 and std≈1."""
        np.random.seed(42)
        s = pd.Series(np.random.normal(100, 15, 1000))
        result = zscore_standardize(s)
        assert abs(result.mean()) < 0.01
        assert abs(result.std() - 1.0) < 0.05

    def test_nan_passthrough(self):
        """NaN values should remain NaN after z-scoring."""
        s = pd.Series([1, 2, np.nan, 4, 5])
        result = zscore_standardize(s)
        assert np.isnan(result.iloc[2])
        # Non-NaN values should be valid floats
        assert not np.isnan(result.iloc[0])

    def test_all_nan_returns_all_nan(self):
        """All-NaN series should stay all-NaN."""
        s = pd.Series([np.nan, np.nan, np.nan])
        result = zscore_standardize(s)
        assert result.isna().all()

    def test_constant_series_returns_nan(self):
        """Constant series (std=0) should return all NaN."""
        s = pd.Series([5.0, 5.0, 5.0, 5.0])
        result = zscore_standardize(s)
        assert result.isna().all()

    def test_empty_series(self):
        """Empty series should return empty series."""
        s = pd.Series([], dtype=float)
        result = zscore_standardize(s)
        assert len(result) == 0


class TestStandardizeFactors:
    def test_standardizes_specified_columns(self):
        """Only specified factor columns should be standardized."""
        df = pd.DataFrame({
            "stock_code": ["A", "B", "C", "D"],
            "momentum_5d": [1.0, 2.0, 3.0, 100.0],  # outlier
            "roe": [10.0, 20.0, 30.0, 40.0],
            "name": ["a", "b", "c", "d"],
        })
        result = standardize_factors(df, ["momentum_5d", "roe"])
        # stock_code and name should be unchanged
        assert list(result["stock_code"]) == ["A", "B", "C", "D"]
        assert list(result["name"]) == ["a", "b", "c", "d"]
        # Factor columns should be standardized (mean≈0)
        assert abs(result["momentum_5d"].mean()) < 0.01
        assert abs(result["roe"].mean()) < 0.01

    def test_missing_column_skipped(self):
        """Columns not in DataFrame should be silently skipped."""
        df = pd.DataFrame({"momentum_5d": [1.0, 2.0, 3.0]})
        result = standardize_factors(df, ["momentum_5d", "nonexistent"])
        assert "nonexistent" not in result.columns
