"""Position sizing engine: Kelly fraction + volatility adjustment + lot rounding."""
import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from loguru import logger

from trading_system.strategies.base import MarketState, Signal, STRATEGY_WEIGHTS


@dataclass
class PositionOrder:
    signal: Signal
    target_pct: float       # target portfolio weight (0-1)
    shares: int             # actual shares (rounded to 100-lot)
    actual_pct: float       # actual weight after rounding


# Default position when no win-rate history available
DEFAULT_BASE_PCT = 0.10     # confidence * 10% = base position


class PositionSizer:
    """Three-level position sizing: total → strategy → individual stock."""

    def __init__(self, total_capital: float = 1_000_000):
        self.total_capital = total_capital

    def size(self, signals: list[Signal], market_state: MarketState,
             portfolio, factor_df: pd.DataFrame = None,
             position_limit_override: float = None) -> list[PositionOrder]:
        """Size positions for a list of signals.

        Args:
            signals: filtered signals to size
            market_state: current market regime
            portfolio: Portfolio object (for current positions)
            factor_df: factor_cache data (for volatility adjustment)
            position_limit_override: forced position limit from drawdown monitor

        Returns:
            list of PositionOrder with shares rounded to 100-lot
        """
        if not signals:
            return []

        weights = STRATEGY_WEIGHTS[market_state]

        # Level 1: total position limit
        total_limit = weights["position_limit"]
        if position_limit_override is not None:
            total_limit = min(total_limit, position_limit_override)

        current_position_pct = portfolio.get_total_position_pct() if portfolio else 0.0
        available_pct = max(0, total_limit - current_position_pct)

        if available_pct <= 0:
            logger.info("No available capacity, skipping all signals")
            return []

        # Compute raw weights per signal
        raw_weights = []
        for sig in signals:
            w = self._calc_raw_weight(sig, weights, factor_df)
            raw_weights.append(w)

        # Normalize: total raw weights should not exceed available_pct
        total_raw = sum(raw_weights)
        if total_raw > available_pct:
            scale = available_pct / total_raw
            raw_weights = [w * scale for w in raw_weights]

        # Build orders with lot rounding
        total_value = portfolio.get_total_value_estimate() if portfolio else self.total_capital
        orders = []
        for sig, target_pct in zip(signals, raw_weights):
            if target_pct < 0.005:  # skip < 0.5%
                continue

            # Skip signals with invalid entry_price
            if pd.isna(sig.entry_price) or sig.entry_price <= 0:
                logger.warning(f"Skipping {sig.stock_code} due to invalid entry_price: {sig.entry_price}")
                continue

            shares = self._round_to_lot(total_value, target_pct, sig.entry_price)
            if shares == 0:
                continue

            actual_pct = (shares * sig.entry_price) / total_value if total_value > 0 else 0
            orders.append(PositionOrder(
                signal=sig,
                target_pct=round(target_pct, 4),
                shares=shares,
                actual_pct=round(actual_pct, 4),
            ))

        logger.info(f"Sized {len(orders)} orders, total target={sum(o.actual_pct for o in orders):.1%}")
        return orders

    def _calc_raw_weight(self, signal: Signal, weights: dict,
                         factor_df: pd.DataFrame = None) -> float:
        """Calculate raw position weight for a single signal."""
        # Base: confidence × default allocation
        base = signal.confidence * DEFAULT_BASE_PCT

        # Strategy allocation cap
        strategy_cap = weights.get(signal.strategy, 0.05)

        # Volatility inverse weighting
        vol_adj = 1.0
        if factor_df is not None and not factor_df.empty:
            code = signal.stock_code
            if code in factor_df.index and "volatility_20d" in factor_df.columns:
                stock_vol = factor_df.at[code, "volatility_20d"]
                if stock_vol and not np.isnan(stock_vol) and stock_vol > 0:
                    median_vol = factor_df["volatility_20d"].median()
                    if median_vol and median_vol > 0:
                        vol_adj = min(median_vol / stock_vol, 2.0)

        weighted = base * signal.direction * vol_adj

        # Cap by: single stock 15%, strategy allocation
        return min(weighted, 0.15, strategy_cap)

    @staticmethod
    def _round_to_lot(total_value: float, pct: float, price: float,
                      lot_size: int = 100) -> int:
        """Round position to A-share 100-lot size."""
        try:
            # Check all inputs for NaN
            if pd.isna(total_value) or pd.isna(pct) or pd.isna(price):
                return 0
            if price <= 0 or total_value <= 0 or pct <= 0:
                return 0

            target_amount = total_value * pct
            if pd.isna(target_amount):
                return 0

            shares = math.floor(target_amount / price / lot_size) * lot_size
            return max(shares, 0)
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid values in _round_to_lot: total_value={total_value}, pct={pct}, price={price}, error={e}")
            return 0
