"""Fundamental factor computation functions.

Functions extract or compute fundamental factors from financial data.
Each returns a pd.Series indexed by stock code.
"""
import numpy as np
import pandas as pd
from trading_system.factors.utils import safe_div_series


# --- Direct extraction from financial_summary ---

def get_roe(summary_df: pd.DataFrame) -> pd.Series:
    """Extract ROE from financial_summary."""
    if summary_df.empty or "roe" not in summary_df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(summary_df["roe"], errors="coerce").astype(float)


def get_gross_margin(summary_df: pd.DataFrame) -> pd.Series:
    """Extract gross_margin from financial_summary."""
    if summary_df.empty or "gross_margin" not in summary_df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(summary_df["gross_margin"], errors="coerce").astype(float)


def get_net_margin(summary_df: pd.DataFrame) -> pd.Series:
    """Extract net_margin from financial_summary."""
    if summary_df.empty or "net_margin" not in summary_df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(summary_df["net_margin"], errors="coerce").astype(float)


def get_debt_ratio(summary_df: pd.DataFrame) -> pd.Series:
    """Extract debt_to_assets from financial_summary."""
    if summary_df.empty or "debt_to_assets" not in summary_df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(summary_df["debt_to_assets"], errors="coerce").astype(float)


def get_revenue_growth(summary_df: pd.DataFrame) -> pd.Series:
    """Extract revenue_growth from financial_summary."""
    if summary_df.empty or "revenue_growth" not in summary_df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(summary_df["revenue_growth"], errors="coerce").astype(float)


def get_profit_growth(summary_df: pd.DataFrame) -> pd.Series:
    """Extract earnings_growth from financial_summary."""
    if summary_df.empty or "earnings_growth" not in summary_df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(summary_df["earnings_growth"], errors="coerce").astype(float)


# --- Direct extraction from stock_valuation ---

def get_pe_ttm(valuation_df: pd.DataFrame) -> pd.Series:
    """Extract pe_ttm from stock_valuation."""
    if valuation_df.empty or "pe_ttm" not in valuation_df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(valuation_df["pe_ttm"], errors="coerce").astype(float)


def get_pb(valuation_df: pd.DataFrame) -> pd.Series:
    """Extract pb from stock_valuation."""
    if valuation_df.empty or "pb" not in valuation_df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(valuation_df["pb"], errors="coerce").astype(float)


def get_ps_ttm(valuation_df: pd.DataFrame) -> pd.Series:
    """Extract ps_ttm from stock_valuation."""
    if valuation_df.empty or "ps_ttm" not in valuation_df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(valuation_df["ps_ttm"], errors="coerce").astype(float)


# --- Computed from financial statements ---

def calc_ocf_to_profit(cashflow_df: pd.DataFrame, income_df: pd.DataFrame) -> pd.Series:
    """Operating cashflow / net profit ratio."""
    if cashflow_df.empty or income_df.empty:
        return pd.Series(dtype=float)
    ocf = pd.to_numeric(cashflow_df["act_cash_flow_net"], errors="coerce")
    np_ = pd.to_numeric(income_df["net_profit"], errors="coerce")
    # Align indices (both indexed by code)
    ocf, np_ = ocf.align(np_, join="inner")
    return safe_div_series(ocf, np_)


def calc_accrual_ratio(income_df: pd.DataFrame, cashflow_df: pd.DataFrame,
                       balance_df: pd.DataFrame) -> pd.Series:
    """Accrual ratio: (net_profit - OCF) / total_assets."""
    if income_df.empty or cashflow_df.empty or balance_df.empty:
        return pd.Series(dtype=float)
    np_ = pd.to_numeric(income_df["net_profit"], errors="coerce")
    ocf = pd.to_numeric(cashflow_df["act_cash_flow_net"], errors="coerce")
    assets = pd.to_numeric(balance_df["assets_total"], errors="coerce")
    # Align all three
    accrual = np_.subtract(ocf, fill_value=0)
    accrual, assets = accrual.align(assets, join="inner")
    return safe_div_series(accrual, assets)


def calc_goodwill_ratio(balance_df: pd.DataFrame) -> pd.Series:
    """Goodwill / total equity."""
    if balance_df.empty:
        return pd.Series(dtype=float)
    goodwill = pd.to_numeric(balance_df.get("goodwill", pd.Series(dtype=float)), errors="coerce")
    equity = pd.to_numeric(balance_df["holder_equity_total"], errors="coerce")
    # Treat missing goodwill as 0
    goodwill = goodwill.fillna(0)
    return safe_div_series(goodwill, equity)


def calc_dividend_yield(dividend_df: pd.DataFrame, valuation_df: pd.DataFrame) -> pd.Series:
    """Dividend yield: (dividend_per_10 / 10) / latest_price."""
    if dividend_df.empty or valuation_df.empty:
        return pd.Series(dtype=float)
    dps = pd.to_numeric(dividend_df["dividend_per_10"], errors="coerce") / 10.0
    price = pd.to_numeric(valuation_df["latest_price"], errors="coerce")
    dps, price = dps.align(price, join="inner")
    return safe_div_series(dps, price)


# --- New fundamental factors ---

def calc_roa(income_df: pd.DataFrame, balance_df: pd.DataFrame) -> pd.Series:
    """Return on Assets: net_profit / total_assets."""
    if income_df.empty or balance_df.empty:
        return pd.Series(dtype=float)
    np_ = pd.to_numeric(income_df["net_profit"], errors="coerce")
    assets = pd.to_numeric(balance_df["assets_total"], errors="coerce")
    np_, assets = np_.align(assets, join="inner")
    return safe_div_series(np_, assets)


def calc_current_ratio(balance_df: pd.DataFrame) -> pd.Series:
    """Current ratio: total_current_assets / current_total_debt."""
    if balance_df.empty:
        return pd.Series(dtype=float)
    current_assets = pd.to_numeric(balance_df.get("total_current_assets", pd.Series(dtype=float)), errors="coerce")
    current_debt = pd.to_numeric(balance_df.get("current_total_debt", pd.Series(dtype=float)), errors="coerce")
    return safe_div_series(current_assets, current_debt)


def calc_peg(valuation_df: pd.DataFrame, summary_df: pd.DataFrame) -> pd.Series:
    """PEG: PE_TTM / earnings_growth. Lower PEG = cheaper growth."""
    if valuation_df.empty or summary_df.empty:
        return pd.Series(dtype=float)
    pe = pd.to_numeric(valuation_df.get("pe_ttm", pd.Series(dtype=float)), errors="coerce")
    growth = pd.to_numeric(summary_df.get("earnings_growth", pd.Series(dtype=float)), errors="coerce")
    pe, growth = pe.align(growth, join="inner")
    # Only meaningful when PE > 0 and growth > 0
    result = safe_div_series(pe, growth)
    result[(pe <= 0) | (growth <= 0)] = np.nan
    return result


def calc_market_cap_pct(valuation_df: pd.DataFrame) -> pd.Series:
    """Market cap percentile rank (cross-sectional). Range: 0-1."""
    if valuation_df.empty or "total_market_cap" not in valuation_df.columns:
        return pd.Series(dtype=float)
    mcap = pd.to_numeric(valuation_df["total_market_cap"], errors="coerce")
    return mcap.rank(pct=True)

