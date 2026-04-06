import numpy as np
import pandas as pd


def safe_div(a, b):
    """Safe division returning NaN on zero/None/NaN."""
    if b is None or (isinstance(b, (int, float)) and (b == 0 or np.isnan(b))):
        return np.nan
    if a is None or (isinstance(a, (int, float)) and np.isnan(a)):
        return np.nan
    return a / b


def safe_div_series(a: pd.Series, b: pd.Series) -> pd.Series:
    """Element-wise safe division for Series."""
    return a / b.replace(0, np.nan)


def require_min_rows(df: pd.DataFrame, n: int, name: str = "data") -> bool:
    """Check if DataFrame has at least n rows. Returns True if OK."""
    if len(df) < n:
        return False
    return True
