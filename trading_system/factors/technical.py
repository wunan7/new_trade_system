"""Technical factor computation functions.

All functions take pandas Series from a single stock's OHLCV data
and return a pandas Series of the same length (with NaN for warmup period).
"""
import numpy as np
import pandas as pd


def momentum_nd(close: pd.Series, n: int) -> pd.Series:
    """N-day price return: (close / close.shift(n)) - 1"""
    return close / close.shift(n) - 1


def volatility_nd(close: pd.Series, n: int, annualize: bool = True) -> pd.Series:
    """Rolling N-day annualized volatility of daily returns."""
    returns = close.pct_change()
    vol = returns.rolling(n).std()
    if annualize:
        vol = vol * np.sqrt(252)
    return vol


def atr_14d(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average True Range. Delegates to finance_data."""
    from finance_data.indicators.technical import calc_atr
    return calc_atr(high, low, close, period=period)


def volume_ratio_5d(volume: pd.Series, n: int = 5) -> pd.Series:
    """Today's volume divided by N-day average volume."""
    avg = volume.rolling(n).mean()
    return volume / avg


def turnover_deviation(turnover: pd.Series, n: int = 20) -> pd.Series:
    """Turnover z-score deviation from N-day rolling mean."""
    mean = turnover.rolling(n).mean()
    std = turnover.rolling(n).std()
    # Replace zero std with NaN to avoid division by zero
    std = std.replace(0, np.nan)
    return (turnover - mean) / std


# --- Trend & Relative Strength factors ---

def macd_signal(close: pd.Series) -> pd.Series:
    """MACD DIF value. Delegates to finance_data."""
    from finance_data.indicators.technical import calc_macd
    dif, _, _ = calc_macd(close)
    return dif


def adx_14d(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """14-day ADX trend strength indicator. Delegates to finance_data."""
    from finance_data.indicators.technical import calc_adx
    return calc_adx(high, low, close, period=period)


def bb_width(close: pd.Series, period: int = 20, std_dev: int = 2) -> pd.Series:
    """Bollinger Band width: (upper - lower) / middle."""
    from finance_data.indicators.technical import calc_bollinger
    upper, middle, lower = calc_bollinger(close, period=period, std_dev=std_dev)
    return (upper - lower) / middle.replace(0, np.nan)


def rs_vs_index(stock_close: pd.Series, index_close: pd.Series, n: int = 20) -> pd.Series:
    """Relative strength vs index: stock n-day return - index n-day return."""
    stock_ret = stock_close / stock_close.shift(n) - 1
    index_ret = index_close / index_close.shift(n) - 1
    # Align by index (trade_date)
    stock_ret, index_ret = stock_ret.align(index_ret, join="inner")
    return stock_ret - index_ret


def obv_slope(close: pd.Series, volume: pd.Series, n: int = 20) -> pd.Series:
    """OBV 20-day linear regression slope.

    OBV = cumulative sum of volume * sign(price change).
    Slope is computed via rolling linear regression (polyfit degree 1).
    """
    # Compute OBV
    sign = np.sign(close.diff()).fillna(0)
    obv = (volume * sign).cumsum()

    # Rolling linear regression slope
    def _rolling_slope(s):
        if len(s) < n or s.isna().any():
            return np.nan
        x = np.arange(len(s))
        try:
            slope, _ = np.polyfit(x, s.values, 1)
            return slope
        except Exception:
            return np.nan

    return obv.rolling(n).apply(_rolling_slope, raw=False)


# --- New technical factors ---

def amplitude_nd(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 20) -> pd.Series:
    """N-day average amplitude: mean((high - low) / prev_close)."""
    prev_close = close.shift(1)
    daily_amp = (high - low) / prev_close.replace(0, np.nan)
    return daily_amp.rolling(n).mean()


def upper_shadow_ratio(open_: pd.Series, high: pd.Series, close: pd.Series,
                       low: pd.Series, n: int = 20) -> pd.Series:
    """N-day average upper shadow ratio: (high - max(open, close)) / (high - low)."""
    body_top = pd.concat([open_, close], axis=1).max(axis=1)
    hl_range = (high - low).replace(0, np.nan)
    shadow = (high - body_top) / hl_range
    return shadow.rolling(n).mean()


def ma_alignment(close: pd.Series) -> pd.Series:
    """Moving average alignment score: count of MA5>MA10>MA20>MA60 conditions met (0-3)."""
    ma5 = close.rolling(5).mean()
    ma10 = close.rolling(10).mean()
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()
    score = (ma5 > ma10).astype(float) + (ma10 > ma20).astype(float) + (ma20 > ma60).astype(float)
    # Set NaN where ma60 is NaN (warmup period)
    score[ma60.isna()] = np.nan
    return score


def volume_price_corr(close: pd.Series, volume: pd.Series, n: int = 20) -> pd.Series:
    """Rolling correlation between close price changes and volume over n days."""
    ret = close.pct_change()
    return ret.rolling(n).corr(volume)

