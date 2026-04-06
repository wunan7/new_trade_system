"""Bulk data loading from finance database for factor computation."""
from datetime import date, timedelta
import pandas as pd
from sqlalchemy import text
from loguru import logger


class FactorDataLoader:
    """Loads cross-sectional data for a given trade_date."""

    def __init__(self, engine, lookback_days: int = 120):
        self.engine = engine
        self.lookback_days = lookback_days

    def load_stock_list(self, exclude_st: bool = True) -> list[str]:
        """Load active stock codes from stock_info."""
        sql = "SELECT code FROM stock_info WHERE is_active = true"
        if exclude_st:
            sql += " AND is_st = false"
        sql += " ORDER BY code"
        with self.engine.connect() as conn:
            result = conn.execute(text(sql))
            return [row[0] for row in result]

    def load_daily_prices(self, trade_date: date, stock_codes: list[str] = None) -> dict[str, pd.DataFrame]:
        """Load OHLCV data for all stocks from (trade_date - lookback) to trade_date.

        Returns dict: {stock_code: DataFrame with OHLCV columns, indexed by trade_date}
        Uses raw SQL + pd.read_sql for performance.
        """
        start_date = trade_date - timedelta(days=int(self.lookback_days * 1.6))  # extra margin for non-trading days

        sql = """
            SELECT code, trade_date, open, high, low, close, volume, amount, pct_change, turnover
            FROM stock_daily
            WHERE trade_date BETWEEN :start_date AND :trade_date
        """
        params = {"start_date": start_date, "trade_date": trade_date}

        if stock_codes:
            sql += " AND code IN :codes"
            params["codes"] = tuple(stock_codes)

        sql += " ORDER BY code, trade_date"

        df = pd.read_sql(text(sql), self.engine, params=params)
        if df.empty:
            return {}

        # Group by stock code, return dict of DataFrames indexed by trade_date
        result = {}
        for code, group in df.groupby("code"):
            group = group.set_index("trade_date").sort_index()
            # Keep only last `lookback_days` trading days
            group = group.tail(self.lookback_days)
            result[code] = group

        logger.info(f"Loaded daily prices for {len(result)} stocks, {len(df)} total rows")
        return result

    def load_index_prices(self, trade_date: date, index_code: str = "000300") -> pd.DataFrame:
        """Load index daily prices for relative strength calculation."""
        start_date = trade_date - timedelta(days=int(self.lookback_days * 1.6))
        sql = """
            SELECT trade_date, open, high, low, close, volume, amount
            FROM index_daily
            WHERE code = :code AND trade_date BETWEEN :start_date AND :trade_date
            ORDER BY trade_date
        """
        df = pd.read_sql(text(sql), self.engine, params={
            "code": index_code, "start_date": start_date, "trade_date": trade_date
        })
        if df.empty:
            return pd.DataFrame()
        df = df.set_index("trade_date").sort_index().tail(self.lookback_days)
        return df

    def load_financial_summary(self, trade_date: date) -> pd.DataFrame:
        """Load latest financial_summary per stock as of trade_date.

        Uses DISTINCT ON to get the most recent report for each stock.
        Returns DataFrame indexed by code.
        """
        sql = """
            SELECT DISTINCT ON (code) code, report_date, roe, gross_margin, net_margin,
                   debt_to_assets, revenue_growth, earnings_growth
            FROM financial_summary
            WHERE report_date <= :trade_date
            ORDER BY code, report_date DESC
        """
        df = pd.read_sql(text(sql), self.engine, params={"trade_date": trade_date})
        if df.empty:
            return pd.DataFrame()
        df = df.set_index("code")
        # Convert Decimal to float
        for col in df.select_dtypes(include=["object"]).columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        logger.info(f"Loaded financial summary for {len(df)} stocks")
        return df

    def load_financial_statements(self, trade_date: date) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Load latest income/balance/cashflow per stock.

        Returns (income_df, balance_df, cashflow_df), each indexed by code.
        """
        income_sql = """
            SELECT DISTINCT ON (code) code, report_date, net_profit
            FROM financial_income
            WHERE report_date <= :trade_date
            ORDER BY code, report_date DESC
        """
        balance_sql = """
            SELECT DISTINCT ON (code) code, report_date, assets_total, goodwill, holder_equity_total
            FROM financial_balance
            WHERE report_date <= :trade_date
            ORDER BY code, report_date DESC
        """
        cashflow_sql = """
            SELECT DISTINCT ON (code) code, report_date, act_cash_flow_net
            FROM financial_cashflow
            WHERE report_date <= :trade_date
            ORDER BY code, report_date DESC
        """
        params = {"trade_date": trade_date}

        income_df = pd.read_sql(text(income_sql), self.engine, params=params)
        balance_df = pd.read_sql(text(balance_sql), self.engine, params=params)
        cashflow_df = pd.read_sql(text(cashflow_sql), self.engine, params=params)

        for df in [income_df, balance_df, cashflow_df]:
            if not df.empty:
                df.set_index("code", inplace=True)
                for col in df.select_dtypes(include=["object"]).columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

        logger.info(f"Loaded financial statements: income={len(income_df)}, balance={len(balance_df)}, cashflow={len(cashflow_df)}")
        return income_df, balance_df, cashflow_df

    def load_valuation(self, trade_date: date) -> pd.DataFrame:
        """Load stock_valuation for exact trade_date.

        Returns DataFrame indexed by code. Empty if no data (sparse history).
        """
        sql = """
            SELECT code, pe_ttm, pb, ps_ttm, latest_price, total_market_cap, circulating_market_cap
            FROM stock_valuation
            WHERE trade_date = :trade_date
        """
        df = pd.read_sql(text(sql), self.engine, params={"trade_date": trade_date})
        if df.empty:
            logger.warning(f"No valuation data for {trade_date}")
            return pd.DataFrame()
        df = df.set_index("code")
        for col in df.select_dtypes(include=["object"]).columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df

    def load_money_flow(self, trade_date: date) -> pd.DataFrame:
        """Load money_flow data for recent 20 trading days up to trade_date.

        Returns DataFrame with columns: code, trade_date, north_net_buy, north_hold_pct,
        main_net_inflow, margin_balance. Not indexed (multiple rows per code).
        """
        sql = """
            SELECT code, trade_date, north_net_buy, north_hold_pct, main_net_inflow, margin_balance
            FROM money_flow
            WHERE trade_date <= :trade_date
            ORDER BY trade_date DESC
        """
        # We need recent 20 trading days; fetch with a generous date window
        start_date = trade_date - timedelta(days=40)
        sql = """
            SELECT code, trade_date, north_net_buy, north_hold_pct, main_net_inflow, margin_balance
            FROM money_flow
            WHERE trade_date BETWEEN :start_date AND :trade_date
            ORDER BY code, trade_date
        """
        df = pd.read_sql(text(sql), self.engine, params={
            "start_date": start_date, "trade_date": trade_date
        })
        if df.empty:
            logger.warning(f"No money_flow data for {trade_date}")
            return pd.DataFrame()

        # Keep only last 20 trading days
        unique_dates = sorted(df["trade_date"].unique())
        recent_dates = unique_dates[-20:]
        df = df[df["trade_date"].isin(recent_dates)]

        for col in ["north_net_buy", "main_net_inflow", "margin_balance"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        logger.info(f"Loaded money_flow: {len(df)} rows, {df['code'].nunique()} stocks, {len(recent_dates)} days")
        return df

    def load_daily_amount(self, trade_date: date) -> pd.Series:
        """Load daily trading amount for all stocks on trade_date.

        Returns Series indexed by code, values in yuan.
        """
        sql = """
            SELECT code, amount
            FROM stock_daily
            WHERE trade_date = :trade_date
        """
        df = pd.read_sql(text(sql), self.engine, params={"trade_date": trade_date})
        if df.empty:
            return pd.Series(dtype=float)
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
        return df.set_index("code")["amount"]

    def load_dividends(self) -> pd.DataFrame:
        """Load most recent dividend per stock.

        Returns DataFrame indexed by code with dividend_per_10 column.
        """
        sql = """
            SELECT DISTINCT ON (code) code, report_year, dividend_per_10
            FROM stock_dividend
            WHERE dividend_per_10 > 0
            ORDER BY code, report_year DESC
        """
        df = pd.read_sql(text(sql), self.engine)
        if df.empty:
            return pd.DataFrame()
        df = df.set_index("code")
        for col in df.select_dtypes(include=["object"]).columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df
