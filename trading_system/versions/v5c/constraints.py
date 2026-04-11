"""Hard constraint filtering for trading signals."""
from datetime import date, timedelta
import pandas as pd
from sqlalchemy import text
from loguru import logger


# Constraint thresholds
MIN_LISTING_DAYS = 60           # exclude stocks listed < 60 trading days
MIN_AVG_AMOUNT = 5_000_000     # 20-day average daily amount >= 500万 yuan
MAX_SINGLE_POSITION = 0.15     # single stock <= 15% of portfolio
MAX_INDUSTRY_POSITION = 0.30   # single industry <= 30% of portfolio


class ConstraintFilter:
    """Filter signals by hard constraints before position sizing."""

    def __init__(self, engine):
        self.engine = engine

    def filter(self, signals, trade_date: date,
               portfolio=None) -> tuple[list, list]:
        """Filter signals, return (passed, rejected_with_reason).

        Args:
            signals: list of Signal objects
            trade_date: the trading date
            portfolio: Portfolio object for position/industry checks (optional)

        Returns:
            (passed_signals, list of (signal, reason_string))
        """
        if not signals:
            return [], []

        codes = [s.stock_code for s in signals]

        # Load constraint data
        constraints = self._load_trade_constraints(trade_date, codes)
        listing_info = self._load_listing_info(codes, trade_date)
        liquidity = self._load_liquidity(trade_date, codes)

        passed = []
        rejected = []

        for signal in signals:
            code = signal.stock_code
            reason = self._check_signal(
                code, trade_date, constraints, listing_info, liquidity, portfolio
            )
            if reason:
                rejected.append((signal, reason))
            else:
                passed.append(signal)

        logger.info(f"Constraint filter: {len(passed)} passed, {len(rejected)} rejected")
        return passed, rejected

    def _check_signal(self, code: str, trade_date: date,
                      constraints: dict, listing_info: dict,
                      liquidity: dict, portfolio) -> str | None:
        """Check a single stock against all constraints. Returns reason or None."""
        tc = constraints.get(code)

        # ST check
        if tc and tc.get("is_st"):
            return "ST"

        # Suspended check
        if tc and tc.get("is_suspended"):
            return "suspended"

        # Limit-up check (can't buy at limit-up)
        if tc and tc.get("is_limit_up"):
            return "limit_up"

        # New stock check
        info = listing_info.get(code)
        if info and info.get("days_listed", 999) < MIN_LISTING_DAYS:
            return f"new_stock({info['days_listed']}d)"

        # Liquidity check
        avg_amount = liquidity.get(code, 0)
        if avg_amount < MIN_AVG_AMOUNT:
            return f"low_liquidity({avg_amount/1e4:.0f}w)"

        # Portfolio constraints
        if portfolio is not None:
            # Single stock position limit
            current_pct = portfolio.get_position_pct(code)
            if current_pct >= MAX_SINGLE_POSITION:
                return f"position_limit({current_pct:.1%})"

            # Industry concentration limit
            industry = info.get("industry") if info else None
            if industry:
                industry_pct = portfolio.get_industry_pct(industry)
                if industry_pct >= MAX_INDUSTRY_POSITION:
                    return f"industry_limit({industry}:{industry_pct:.1%})"

        return None

    def _load_trade_constraints(self, trade_date: date, codes: list[str]) -> dict:
        """Load trade_constraints for given codes on trade_date."""
        if not codes:
            return {}
        sql = """
            SELECT tc.code, tc.is_suspended, tc.is_st, tc.up_limit,
                   sd.close
            FROM trade_constraints tc
            LEFT JOIN stock_daily sd ON tc.code = sd.code AND sd.trade_date = :td
            WHERE tc.trade_date = :td AND tc.code IN :codes
        """
        with self.engine.connect() as conn:
            result = conn.execute(text(sql), {"td": trade_date, "codes": tuple(codes)})
            out = {}
            for row in result:
                close = float(row[4]) if row[4] else None
                up_limit = float(row[3]) if row[3] else None
                is_limit_up = (close and up_limit and close >= up_limit)
                out[row[0]] = {
                    "is_suspended": row[1],
                    "is_st": row[2],
                    "is_limit_up": is_limit_up,
                }
            return out

    def _load_listing_info(self, codes: list[str], trade_date: date) -> dict:
        """Load listing date and industry for given codes."""
        if not codes:
            return {}
        sql = """
            SELECT code, list_date, industry_l1
            FROM stock_info
            WHERE code IN :codes
        """
        with self.engine.connect() as conn:
            result = conn.execute(text(sql), {"codes": tuple(codes)})
            out = {}
            for row in result:
                list_date = row[1]
                days = (trade_date - list_date).days if list_date else 9999
                out[row[0]] = {"days_listed": days, "industry": row[2]}
            return out

    def _load_liquidity(self, trade_date: date, codes: list[str]) -> dict:
        """Load 20-day average daily trading amount for given codes."""
        if not codes:
            return {}
        start = trade_date - timedelta(days=40)
        sql = """
            SELECT code, AVG(amount) as avg_amount
            FROM stock_daily
            WHERE trade_date BETWEEN :start AND :td AND code IN :codes
            GROUP BY code
        """
        with self.engine.connect() as conn:
            result = conn.execute(text(sql), {"start": start, "td": trade_date, "codes": tuple(codes)})
            return {row[0]: float(row[1]) if row[1] else 0 for row in result}
