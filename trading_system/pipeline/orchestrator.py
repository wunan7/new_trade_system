"""Factor pipeline orchestrator: load → compute → standardize → write."""
import json
from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd
from loguru import logger
from sqlalchemy.orm import Session

from trading_system.db.models import FactorCache
from trading_system.factors import technical as tech
from trading_system.factors import fundamental as fund
from trading_system.factors import money_flow as mflow
from trading_system.factors import sentiment as sent
from trading_system.factors.registry import get_all_factor_names
from trading_system.pipeline.data_loader import FactorDataLoader
from trading_system.pipeline.standardizer import standardize_factors
from trading_system.pipeline.writer import write_factor_cache


class _DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        if isinstance(o, (np.floating, np.integer)):
            return float(o)
        return super().default(o)


class FactorPipeline:
    """Main orchestrator: loads data, computes factors, standardizes, writes to DB."""

    TECHNICAL_FACTORS = [
        "momentum_5d", "momentum_20d", "momentum_60d",
        "volatility_20d", "volatility_60d", "atr_14d",
        "volume_ratio_5d", "turnover_dev", "macd_signal",
        "adx", "bb_width", "rs_vs_index", "obv_slope",
        "amplitude_20d", "upper_shadow_ratio", "ma_alignment", "volume_price_corr",
    ]
    FUNDAMENTAL_FACTORS = [
        "roe", "gross_margin", "net_margin", "debt_ratio",
        "revenue_growth", "profit_growth",
        "ocf_to_profit", "accrual_ratio", "goodwill_ratio",
        "pe_ttm", "pb", "ps_ttm", "dividend_yield",
        "roa", "current_ratio", "peg", "market_cap_pct",
    ]
    MONEY_FLOW_FACTORS = [
        "north_flow_chg", "north_days", "main_net_ratio", "margin_chg_rate",
        "big_order_net_ratio", "consecutive_main_inflow", "margin_buy_ratio",
    ]
    SENTIMENT_FACTORS = [
        "sentiment_score", "news_heat", "news_mention_count",
    ]
    ALL_FACTORS = TECHNICAL_FACTORS + FUNDAMENTAL_FACTORS + MONEY_FLOW_FACTORS + SENTIMENT_FACTORS

    def __init__(self, engine=None):
        if engine is None:
            from trading_system.db.engine import get_engine
            engine = self.engine = get_engine()
        else:
            self.engine = engine
        self.loader = FactorDataLoader(self.engine)

    def run(self, trade_date: date, stock_codes: list[str] = None) -> int:
        """Compute all factors for trade_date, standardize, write to factor_cache.

        Returns number of rows written.
        """
        logger.info(f"Starting factor pipeline for {trade_date}")

        # 1. Load stock list
        if stock_codes is None:
            stock_codes = self.loader.load_stock_list(exclude_st=True)
        logger.info(f"Processing {len(stock_codes)} stocks")

        # 2. Load raw data
        daily_prices = self.loader.load_daily_prices(trade_date, stock_codes)
        index_prices = self.loader.load_index_prices(trade_date, "000300")
        summary_df = self.loader.load_financial_summary(trade_date)
        income_df, balance_df, cashflow_df = self.loader.load_financial_statements(trade_date)
        valuation_df = self.loader.load_valuation(trade_date)
        dividend_df = self.loader.load_dividends()
        mf_df = self.loader.load_money_flow(trade_date)
        daily_amount = self.loader.load_daily_amount(trade_date)

        # 3. Compute technical factors (per-stock, then assemble cross-section)
        tech_df = self._compute_technical_factors(daily_prices, index_prices, trade_date)
        logger.info(f"Technical factors computed for {len(tech_df)} stocks")

        # 4. Compute fundamental factors (cross-sectional)
        fund_df = self._compute_fundamental_factors(
            summary_df, income_df, balance_df, cashflow_df, valuation_df, dividend_df
        )
        logger.info(f"Fundamental factors computed for {len(fund_df)} stocks")

        # 4b. Compute money flow factors (cross-sectional)
        mf_factor_df = self._compute_money_flow_factors(mf_df, valuation_df, daily_amount)
        logger.info(f"Money flow factors computed for {len(mf_factor_df)} stocks")

        # 4c. Compute sentiment factors (cross-sectional)
        sent_factor_df = self._compute_sentiment_factors(daily_prices, trade_date)
        logger.info(f"Sentiment factors computed for {len(sent_factor_df)} stocks")

        # 5. Filter fundamental to requested stocks and merge
        if not fund_df.empty:
            # Filter to only stocks that have technical data or are in requested list
            target_codes = set(stock_codes)
            if not tech_df.empty:
                target_codes = target_codes | set(tech_df.index)
            fund_df = fund_df[fund_df.index.isin(target_codes)]

        if not mf_factor_df.empty:
            target_codes = set(stock_codes)
            if not tech_df.empty:
                target_codes = target_codes | set(tech_df.index)
            mf_factor_df = mf_factor_df[mf_factor_df.index.isin(target_codes)]

        if not sent_factor_df.empty:
            target_codes = set(stock_codes)
            if not tech_df.empty:
                target_codes = target_codes | set(tech_df.index)
            sent_factor_df = sent_factor_df[sent_factor_df.index.isin(target_codes)]

        dfs = [df for df in [tech_df, fund_df, mf_factor_df, sent_factor_df] if not df.empty]
        if not dfs:
            logger.warning("No factors computed, skipping write")
            return 0

        merged = dfs[0]
        for df in dfs[1:]:
            merged = merged.join(df, how="outer")

        # 6. Standardize cross-sectionally
        raw_df = merged.copy()
        std_df = standardize_factors(merged, self.ALL_FACTORS)

        # 7. Build records
        records = self._build_records(trade_date, raw_df, std_df)
        logger.info(f"Built {len(records)} records for writing")

        # 8. Write to DB
        from trading_system.db.engine import session_scope
        with session_scope() as session:
            count = write_factor_cache(session, FactorCache, records)

        logger.info(f"Factor pipeline complete for {trade_date}: {count} rows written")
        return count

    def run_range(self, start_date: date, end_date: date,
                  stock_codes: list[str] = None) -> int:
        """Run pipeline for each trading day in [start_date, end_date]."""
        # Get trading days from stock_daily
        from sqlalchemy import text
        with self.engine.connect() as conn:
            result = conn.execute(text(
                "SELECT DISTINCT trade_date FROM stock_daily "
                "WHERE trade_date BETWEEN :start AND :end "
                "ORDER BY trade_date"
            ), {"start": start_date, "end": end_date})
            trading_days = [row[0] for row in result]

        total = 0
        for i, td in enumerate(trading_days):
            logger.info(f"[{i+1}/{len(trading_days)}] Processing {td}")
            count = self.run(td, stock_codes)
            total += count

        logger.info(f"Range complete: {total} total rows across {len(trading_days)} days")
        return total

    def _compute_technical_factors(self, daily_prices: dict[str, pd.DataFrame],
                                    index_prices: pd.DataFrame,
                                    trade_date: date) -> pd.DataFrame:
        """Compute all technical factors. Returns DataFrame indexed by stock_code."""
        rows = []
        for code, df in daily_prices.items():
            if len(df) < 5:
                continue

            close = df["close"]
            high = df["high"]
            low = df["low"]
            volume = df["volume"].astype(float)
            turnover = df["turnover"].astype(float) if "turnover" in df.columns else pd.Series(dtype=float)

            row = {"stock_code": code}

            # Momentum
            for n in [5, 20, 60]:
                mom = tech.momentum_nd(close, n)
                row[f"momentum_{n}d"] = self._last_value(mom)

            # Volatility
            for n in [20, 60]:
                vol = tech.volatility_nd(close, n)
                row[f"volatility_{n}d"] = self._last_value(vol)

            # ATR
            row["atr_14d"] = self._last_value(tech.atr_14d(high, low, close))

            # Volume
            row["volume_ratio_5d"] = self._last_value(tech.volume_ratio_5d(volume))
            if not turnover.empty:
                row["turnover_dev"] = self._last_value(tech.turnover_deviation(turnover))

            # MACD
            row["macd_signal"] = self._last_value(tech.macd_signal(close))

            # ADX
            row["adx"] = self._last_value(tech.adx_14d(high, low, close))

            # Bollinger
            row["bb_width"] = self._last_value(tech.bb_width(close))

            # Relative Strength vs CSI300
            if not index_prices.empty and "close" in index_prices.columns:
                row["rs_vs_index"] = self._last_value(
                    tech.rs_vs_index(close, index_prices["close"])
                )

            # OBV Slope
            row["obv_slope"] = self._last_value(tech.obv_slope(close, volume))

            # New technical factors
            row["amplitude_20d"] = self._last_value(tech.amplitude_nd(high, low, close, 20))
            open_ = df["open"] if "open" in df.columns else close
            row["upper_shadow_ratio"] = self._last_value(tech.upper_shadow_ratio(open_, high, close, low, 20))
            row["ma_alignment"] = self._last_value(tech.ma_alignment(close))
            row["volume_price_corr"] = self._last_value(tech.volume_price_corr(close, volume, 20))

            rows.append(row)

        if not rows:
            return pd.DataFrame()
        result = pd.DataFrame(rows).set_index("stock_code")
        return result

    def _compute_fundamental_factors(self, summary_df: pd.DataFrame,
                                      income_df: pd.DataFrame,
                                      balance_df: pd.DataFrame,
                                      cashflow_df: pd.DataFrame,
                                      valuation_df: pd.DataFrame,
                                      dividend_df: pd.DataFrame) -> pd.DataFrame:
        """Compute all fundamental factors. Returns DataFrame indexed by stock_code."""
        factors = {}

        # Direct extraction from summary
        if not summary_df.empty:
            factors["roe"] = fund.get_roe(summary_df)
            factors["gross_margin"] = fund.get_gross_margin(summary_df)
            factors["net_margin"] = fund.get_net_margin(summary_df)
            factors["debt_ratio"] = fund.get_debt_ratio(summary_df)
            factors["revenue_growth"] = fund.get_revenue_growth(summary_df)
            factors["profit_growth"] = fund.get_profit_growth(summary_df)

        # Direct extraction from valuation
        if not valuation_df.empty:
            factors["pe_ttm"] = fund.get_pe_ttm(valuation_df)
            factors["pb"] = fund.get_pb(valuation_df)
            factors["ps_ttm"] = fund.get_ps_ttm(valuation_df)

        # Computed from statements
        if not cashflow_df.empty and not income_df.empty:
            factors["ocf_to_profit"] = fund.calc_ocf_to_profit(cashflow_df, income_df)

        if not income_df.empty and not cashflow_df.empty and not balance_df.empty:
            factors["accrual_ratio"] = fund.calc_accrual_ratio(income_df, cashflow_df, balance_df)

        if not balance_df.empty:
            factors["goodwill_ratio"] = fund.calc_goodwill_ratio(balance_df)

        if not dividend_df.empty and not valuation_df.empty:
            factors["dividend_yield"] = fund.calc_dividend_yield(dividend_df, valuation_df)

        # New fundamental factors
        if not income_df.empty and not balance_df.empty:
            factors["roa"] = fund.calc_roa(income_df, balance_df)

        if not balance_df.empty:
            factors["current_ratio"] = fund.calc_current_ratio(balance_df)

        if not valuation_df.empty and not summary_df.empty:
            factors["peg"] = fund.calc_peg(valuation_df, summary_df)

        if not valuation_df.empty:
            factors["market_cap_pct"] = fund.calc_market_cap_pct(valuation_df)

        if not factors:
            return pd.DataFrame()

        result = pd.DataFrame(factors)
        result.index.name = "stock_code"
        return result

    def _compute_money_flow_factors(self, mf_df: pd.DataFrame,
                                     valuation_df: pd.DataFrame,
                                     daily_amount: pd.Series) -> pd.DataFrame:
        """Compute all money flow factors. Returns DataFrame indexed by stock_code."""
        if mf_df.empty:
            return pd.DataFrame()

        factors = {}
        factors["north_flow_chg"] = mflow.calc_north_flow_chg(mf_df, valuation_df)
        factors["north_days"] = mflow.calc_north_days(mf_df)
        factors["main_net_ratio"] = mflow.calc_main_net_ratio(mf_df, daily_amount)
        factors["margin_chg_rate"] = mflow.calc_margin_chg_rate(mf_df)

        # New money flow factors
        factors["big_order_net_ratio"] = mflow.calc_big_order_net_ratio(mf_df, daily_amount)
        factors["consecutive_main_inflow"] = mflow.calc_consecutive_main_inflow(mf_df)
        factors["margin_buy_ratio"] = mflow.calc_margin_buy_ratio(mf_df, daily_amount)

        # Remove empty or all-NaN series
        factors = {k: v for k, v in factors.items() if not v.empty and v.notna().any()}
        if not factors:
            return pd.DataFrame()

        result = pd.DataFrame(factors)
        result.index.name = "stock_code"
        return result

    def _compute_sentiment_factors(self, daily_prices: dict, trade_date: date) -> pd.DataFrame:
        """Compute sentiment factors from TrendRadar."""
        if not daily_prices:
            return pd.DataFrame()

        # Build dummy df with stock codes as index
        codes = list(daily_prices.keys())
        dummy_df = pd.DataFrame(index=codes)
        dummy_df.index.name = "stock_code"

        factors = {}
        factors["sentiment_score"] = sent.sentiment_score(dummy_df, trade_date)
        factors["news_heat"] = sent.news_heat(dummy_df, trade_date)
        factors["news_mention_count"] = sent.news_mention_count(dummy_df, trade_date)

        # Remove empty or all-NaN series
        factors = {k: v for k, v in factors.items() if not v.empty and v.notna().any()}
        if not factors:
            return pd.DataFrame()

        result = pd.DataFrame(factors)
        result.index.name = "stock_code"
        return result

    def _build_records(self, trade_date: date, raw_df: pd.DataFrame,
                       std_df: pd.DataFrame) -> list[dict]:
        """Build list of dicts for DB insertion."""
        records = []
        for code in raw_df.index:
            record = {
                "trade_date": trade_date,
                "stock_code": code,
            }
            raw_vals = {}
            zscore_vals = {}

            for col in self.ALL_FACTORS:
                raw_val = self._to_float(raw_df.at[code, col]) if col in raw_df.columns else None
                std_val = self._to_float(std_df.at[code, col]) if col in std_df.columns else None

                record[col] = raw_val
                if raw_val is not None and not np.isnan(raw_val):
                    raw_vals[col] = round(raw_val, 6)
                if std_val is not None and not np.isnan(std_val):
                    zscore_vals[col] = round(std_val, 6)

            record["factors_json"] = {"raw": raw_vals, "zscore": zscore_vals}
            records.append(record)

        return records

    @staticmethod
    def _last_value(series: pd.Series):
        """Get last non-NaN value from a Series, or NaN."""
        if series is None or series.empty:
            return np.nan
        val = series.iloc[-1]
        if isinstance(val, (Decimal, np.integer, np.floating)):
            val = float(val)
        return val if not (isinstance(val, float) and np.isnan(val)) else np.nan

    @staticmethod
    def _to_float(val) -> float | None:
        """Convert to float, return None for NaN/None."""
        if val is None:
            return None
        try:
            f = float(val)
            return None if np.isnan(f) else f
        except (ValueError, TypeError):
            return None
