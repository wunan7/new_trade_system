"""Backfill only the 10 new factors into existing factor_cache rows.

Much faster than full pipeline recompute since it skips the 33 existing factors.
"""
import sys
import codecs
from datetime import date, timedelta

sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())

import numpy as np
import pandas as pd
from sqlalchemy import text
from loguru import logger

from trading_system.db.engine import get_engine
from trading_system.pipeline.data_loader import FactorDataLoader
from trading_system.factors import technical as tech
from trading_system.factors import fundamental as fund
from trading_system.factors import money_flow as mflow

logger.remove()
logger.add(sys.stderr, level="INFO")

engine = get_engine()
loader = FactorDataLoader(engine)

NEW_FACTORS = [
    "amplitude_20d", "upper_shadow_ratio", "ma_alignment", "volume_price_corr",
    "roa", "current_ratio", "peg", "market_cap_pct",
    "big_order_net_ratio", "consecutive_main_inflow",
]

# Get all trading dates from factor_cache
with engine.connect() as conn:
    dates = [r[0] for r in conn.execute(text(
        "SELECT DISTINCT trade_date FROM factor_cache ORDER BY trade_date"
    ))]

print(f"Backfilling {len(NEW_FACTORS)} new factors for {len(dates)} trading days")


def _last(s):
    if s is None or s.empty:
        return None
    v = s.iloc[-1]
    if pd.isna(v):
        return None
    return round(float(v), 6)


for i, td in enumerate(dates):
    # Load data
    daily_prices = loader.load_daily_prices(td)
    summary_df = loader.load_financial_summary(td)
    income_df, balance_df, cashflow_df = loader.load_financial_statements(td)
    valuation_df = loader.load_valuation(td)
    mf_df = loader.load_money_flow(td)
    daily_amount = loader.load_daily_amount(td)

    # Compute new technical factors per stock
    tech_rows = []
    for code, df in daily_prices.items():
        if len(df) < 5:
            continue
        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"].astype(float)
        open_ = df["open"] if "open" in df.columns else close

        row = {"stock_code": code}
        row["amplitude_20d"] = _last(tech.amplitude_nd(high, low, close, 20))
        row["upper_shadow_ratio"] = _last(tech.upper_shadow_ratio(open_, high, close, low, 20))
        row["ma_alignment"] = _last(tech.ma_alignment(close))
        row["volume_price_corr"] = _last(tech.volume_price_corr(close, volume, 20))
        tech_rows.append(row)

    tech_df = pd.DataFrame(tech_rows).set_index("stock_code") if tech_rows else pd.DataFrame()

    # Compute new fundamental factors
    fund_factors = {}
    if not income_df.empty and not balance_df.empty:
        fund_factors["roa"] = fund.calc_roa(income_df, balance_df)
    if not balance_df.empty:
        fund_factors["current_ratio"] = fund.calc_current_ratio(balance_df)
    if not valuation_df.empty and not summary_df.empty:
        fund_factors["peg"] = fund.calc_peg(valuation_df, summary_df)
    if not valuation_df.empty:
        fund_factors["market_cap_pct"] = fund.calc_market_cap_pct(valuation_df)
    fund_df = pd.DataFrame(fund_factors) if fund_factors else pd.DataFrame()
    if not fund_df.empty:
        fund_df.index.name = "stock_code"

    # Compute new money flow factors
    mflow_factors = {}
    if not mf_df.empty:
        mflow_factors["big_order_net_ratio"] = mflow.calc_big_order_net_ratio(mf_df, daily_amount)
        mflow_factors["consecutive_main_inflow"] = mflow.calc_consecutive_main_inflow(mf_df)
    mflow_df = pd.DataFrame(mflow_factors) if mflow_factors else pd.DataFrame()
    if not mflow_df.empty:
        mflow_df.index.name = "stock_code"

    # Merge all new factors
    all_dfs = [df for df in [tech_df, fund_df, mflow_df] if not df.empty]
    if not all_dfs:
        continue
    merged = all_dfs[0]
    for df in all_dfs[1:]:
        merged = merged.join(df, how="outer")

    # Build UPDATE statements in batch
    updates = []
    for code in merged.index:
        vals = {}
        for col in NEW_FACTORS:
            if col in merged.columns:
                v = merged.at[code, col]
                if pd.notna(v):
                    vals[col] = round(float(v), 6)
        if vals:
            updates.append((code, vals))

    if updates:
        with engine.connect() as conn:
            for code, vals in updates:
                set_clause = ", ".join(f"{k} = :{k}" for k in vals)
                sql = text(f"UPDATE factor_cache SET {set_clause} WHERE trade_date = :td AND stock_code = :code")
                params = {**vals, "td": td, "code": code}
                conn.execute(sql, params)
            conn.commit()

    if (i + 1) % 50 == 0 or i == len(dates) - 1:
        print(f"  [{i+1}/{len(dates)}] {td} - updated {len(updates)} rows")

print("Backfill complete!")
