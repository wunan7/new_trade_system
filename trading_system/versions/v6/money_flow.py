"""Money flow factor computation functions.

Functions compute capital flow factors from money_flow table data.
Each returns a pd.Series indexed by stock code.
"""
import numpy as np
import pandas as pd
from trading_system.factors.utils import safe_div_series


def calc_north_flow_chg(mf_df: pd.DataFrame, valuation_df: pd.DataFrame,
                        n: int = 5) -> pd.Series:
    """North-bound capital inflow intensity over n days.

    Priority: use north_net_buy (real net buy amount in yuan) if available,
    fallback to north_hold_pct change if north_net_buy is mostly NULL.

    Args:
        mf_df: money_flow data with columns [code, trade_date, north_net_buy, north_hold_pct].
        valuation_df: valuation data with circulating_market_cap for normalization.
        n: lookback window (default 5 days).

    Returns:
        Series indexed by code.
    """
    if mf_df.empty:
        return pd.Series(dtype=float)

    dates = sorted(mf_df["trade_date"].unique())
    if len(dates) < 2:
        return pd.Series(dtype=float)

    latest_date = dates[-1]
    recent_dates = dates[-n:] if len(dates) >= n else dates
    recent = mf_df[mf_df["trade_date"].isin(recent_dates)]

    # Check if north_net_buy has real data
    has_north_buy = ("north_net_buy" in recent.columns and
                     pd.to_numeric(recent["north_net_buy"], errors="coerce").notna().sum() > len(recent) * 0.3)

    if has_north_buy:
        # Use real north_net_buy: sum over n days, normalize by circulating market cap
        def _sum_north(group):
            vals = pd.to_numeric(group["north_net_buy"], errors="coerce")
            return vals.sum() if vals.notna().any() else np.nan

        north_sum = recent.groupby("code").apply(_sum_north).astype(float)

        if not valuation_df.empty and "circulating_market_cap" in valuation_df.columns:
            mcap = pd.to_numeric(valuation_df["circulating_market_cap"], errors="coerce")
            north_sum, mcap = north_sum.align(mcap, join="inner")
            return safe_div_series(north_sum, mcap)
        else:
            # Without market cap, return raw sum (less comparable across stocks)
            return north_sum
    else:
        # Fallback: use north_hold_pct change
        if "north_hold_pct" not in mf_df.columns:
            return pd.Series(dtype=float)

        prev_idx = max(0, len(dates) - 1 - n)
        prev_date = dates[prev_idx]

        current = mf_df[mf_df["trade_date"] == latest_date].set_index("code")
        previous = mf_df[mf_df["trade_date"] == prev_date].set_index("code")

        cur_pct = pd.to_numeric(current["north_hold_pct"], errors="coerce")
        prev_pct = pd.to_numeric(previous["north_hold_pct"], errors="coerce")

        pct_chg = cur_pct - prev_pct
        pct_chg = pct_chg.dropna()
        return pct_chg / 100.0


def calc_north_days(mf_df: pd.DataFrame, n: int = 20) -> pd.Series:
    """Ratio of days with positive north-bound flow in last n days.
    Estimated using north_hold_pct day-over-day changes.

    Args:
        mf_df: money_flow data with columns [code, trade_date, north_hold_pct].
        n: lookback window (default 20 days).

    Returns:
        Series indexed by code, values in [0, 1].
    """
    if mf_df.empty or "north_hold_pct" not in mf_df.columns:
        return pd.Series(dtype=float)

    dates = sorted(mf_df["trade_date"].unique())
    # need n+1 days to get n day-over-day changes
    recent_dates = dates[-(n+1):] if len(dates) >= n+1 else dates
    recent = mf_df[mf_df["trade_date"].isin(recent_dates)]

    def _ratio(group):
        group = group.sort_values("trade_date")
        pct = pd.to_numeric(group["north_hold_pct"], errors="coerce")
        pct = pct.dropna()
        if len(pct) < 2:
            return np.nan

        # day-over-day change
        diff = pct.diff().dropna()
        if diff.empty:
            return np.nan

        return (diff > 0).sum() / len(diff)

    return recent.groupby("code").apply(_ratio).astype(float)


def calc_main_net_ratio(mf_df: pd.DataFrame, daily_amount: pd.Series) -> pd.Series:
    """Main capital net inflow / daily trading amount.

    Args:
        mf_df: money_flow data with columns [code, trade_date, main_net_inflow].
               Only the latest date row per code is used.
        daily_amount: Series indexed by code, daily trading amount in yuan from stock_daily.

    Returns:
        Series indexed by code. Both converted to same unit (万元).
    """
    if mf_df.empty or daily_amount.empty:
        return pd.Series(dtype=float)

    # Take the latest date per code
    latest_date = mf_df["trade_date"].max()
    latest = mf_df[mf_df["trade_date"] == latest_date].set_index("code")

    main_inflow = pd.to_numeric(latest["main_net_inflow"], errors="coerce")  # unit: yuan
    amount = pd.to_numeric(daily_amount, errors="coerce")  # unit: yuan

    main_inflow, amount = main_inflow.align(amount, join="inner")
    return safe_div_series(main_inflow, amount)


def calc_margin_chg_rate(mf_df: pd.DataFrame, n: int = 5) -> pd.Series:
    """Margin balance change rate over n days.

    (current margin_balance - n-day-ago margin_balance) / n-day-ago margin_balance.

    Args:
        mf_df: money_flow data with columns [code, trade_date, margin_balance].
        n: lookback period (default 5 days).

    Returns:
        Series indexed by code.
    """
    if mf_df.empty:
        return pd.Series(dtype=float)

    dates = sorted(mf_df["trade_date"].unique())
    if len(dates) < 2:
        return pd.Series(dtype=float)

    latest_date = dates[-1]
    # Find the n-th date back (or earliest available)
    prev_idx = max(0, len(dates) - 1 - n)
    prev_date = dates[prev_idx]

    current = mf_df[mf_df["trade_date"] == latest_date].set_index("code")
    previous = mf_df[mf_df["trade_date"] == prev_date].set_index("code")

    cur_bal = pd.to_numeric(current["margin_balance"], errors="coerce")
    prev_bal = pd.to_numeric(previous["margin_balance"], errors="coerce")

    cur_bal, prev_bal = cur_bal.align(prev_bal, join="inner")
    return safe_div_series(cur_bal - prev_bal, prev_bal)


# --- New money flow factors ---

def calc_big_order_net_ratio(mf_df: pd.DataFrame, daily_amount: pd.Series) -> pd.Series:
    """Big order net inflow ratio: (super_big_net + big_net) / daily_amount.

    Measures large institutional order flow as fraction of total trading.
    """
    if mf_df.empty or daily_amount.empty:
        return pd.Series(dtype=float)

    latest_date = mf_df["trade_date"].max()
    latest = mf_df[mf_df["trade_date"] == latest_date].set_index("code")

    super_big = pd.to_numeric(latest.get("super_big_net", pd.Series(dtype=float)), errors="coerce").fillna(0)
    big = pd.to_numeric(latest.get("big_net", pd.Series(dtype=float)), errors="coerce").fillna(0)
    big_total = super_big + big

    amount = pd.to_numeric(daily_amount, errors="coerce")
    big_total, amount = big_total.align(amount, join="inner")
    return safe_div_series(big_total, amount)


def calc_consecutive_main_inflow(mf_df: pd.DataFrame, n: int = 20) -> pd.Series:
    """Count of consecutive latest days with positive main_net_inflow (up to n days).

    Higher value = sustained institutional buying pressure.
    """
    if mf_df.empty or "main_net_inflow" not in mf_df.columns:
        return pd.Series(dtype=float)

    dates = sorted(mf_df["trade_date"].unique())
    recent_dates = dates[-n:] if len(dates) >= n else dates

    def _count_consecutive(group):
        group = group.sort_values("trade_date", ascending=False)
        inflow = pd.to_numeric(group["main_net_inflow"], errors="coerce")
        count = 0
        for val in inflow:
            if pd.isna(val) or val <= 0:
                break
            count += 1
        return float(count)

    recent = mf_df[mf_df["trade_date"].isin(recent_dates)]
    return recent.groupby("code").apply(_count_consecutive).astype(float)


def calc_margin_buy_ratio(mf_df: pd.DataFrame, daily_amount: pd.Series) -> pd.Series:
    """Margin buy amount / daily trading amount.

    Measures leverage-driven buying pressure as fraction of total trading.
    Higher ratio = more speculative/leveraged buying.

    Args:
        mf_df: money_flow data with columns [code, trade_date, margin_buy].
        daily_amount: Series indexed by code, daily trading amount in yuan.

    Returns:
        Series indexed by code.
    """
    if mf_df.empty or daily_amount.empty:
        return pd.Series(dtype=float)

    if "margin_buy" not in mf_df.columns:
        return pd.Series(dtype=float)

    latest_date = mf_df["trade_date"].max()
    latest = mf_df[mf_df["trade_date"] == latest_date].set_index("code")

    mb = pd.to_numeric(latest["margin_buy"], errors="coerce")
    amount = pd.to_numeric(daily_amount, errors="coerce")

    mb, amount = mb.align(amount, join="inner")
    return safe_div_series(mb, amount)

