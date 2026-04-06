"""Cross-sectional factor standardization: MAD winsorize + z-score."""
import numpy as np
import pandas as pd


def winsorize_mad(series: pd.Series, n: float = 3.0) -> pd.Series:
    """Winsorize using Median Absolute Deviation (MAD).

    Clips values beyond n * MAD from the median.
    MAD is scaled by 1.4826 to approximate standard deviation for normal data.
    NaN values pass through unchanged.
    """
    if series.dropna().empty:
        return series.copy()
    median = series.median()
    mad = (series - median).abs().median() * 1.4826
    if mad == 0:
        return series.copy()
    lower = median - n * mad
    upper = median + n * mad
    return series.clip(lower=lower, upper=upper)


def zscore_standardize(series: pd.Series) -> pd.Series:
    """Cross-sectional z-score standardization.

    Returns (x - mean) / std. NaN where std == 0 or input is NaN.
    """
    if series.dropna().empty:
        return series.copy()
    std = series.std()
    if std == 0 or np.isnan(std):
        return pd.Series(np.nan, index=series.index)
    return (series - series.mean()) / std


def standardize_factors(factor_df: pd.DataFrame, factor_columns: list[str]) -> pd.DataFrame:
    """Apply winsorize_mad then zscore_standardize to each factor column.

    Operates cross-sectionally (all stocks on one date).
    Returns new DataFrame with same index, standardized values.
    Non-factor columns are preserved unchanged.
    """
    result = factor_df.copy()
    for col in factor_columns:
        if col not in result.columns:
            continue
        result[col] = zscore_standardize(winsorize_mad(result[col]))
    return result
