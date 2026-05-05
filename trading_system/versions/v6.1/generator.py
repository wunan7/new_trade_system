"""Signal generation orchestrator."""
from datetime import date
from collections import defaultdict
import numpy as np
import pandas as pd
from loguru import logger
from sqlalchemy import text

from trading_system.strategies.market_state import MarketStateDetector
from trading_system.strategies.value import ValueStrategy
from trading_system.strategies.growth import GrowthStrategy
from trading_system.strategies.momentum import MomentumStrategy
from trading_system.strategies.event_driven import EventDrivenStrategy
from trading_system.strategies.base import Signal, STRATEGY_WEIGHTS
from trading_system.signals.writer import write_signals


# IC/IR-based factor weights for composite alpha scoring (IR >= 0.3)
IC_WEIGHTS = {
    "upper_shadow_ratio": -0.65,
    "momentum_60d": -0.62,
    "turnover_dev": -0.60,
    "pb": -0.55,
    "momentum_20d": -0.55,
    "atr_14d": -0.54,
    "volatility_20d": -0.53,
    "bb_width": -0.52,
    "dividend_yield": 0.50,
    "amplitude_20d": -0.48,
    "ma_alignment": -0.47,
    "market_cap_pct": -0.44,
    "peg": -0.38,
    "accrual_ratio": -0.34,
    "volume_price_corr": -0.30,
}


class SignalGenerator:
    """Main orchestrator: detect market state, run strategies, aggregate, write."""

    def __init__(self, engine=None):
        if engine is None:
            from trading_system.db.engine import get_engine
            engine = get_engine()
        self.engine = engine
        self.detector = MarketStateDetector(engine)
        self.strategies = {
            "value": ValueStrategy(),
            "growth": GrowthStrategy(),
            "momentum": MomentumStrategy(),
            "event": EventDrivenStrategy(engine),
        }

    def _load_factor_df(self, trade_date: date) -> pd.DataFrame:
        """Load factor_cache for the given date."""
        sql = """
            SELECT stock_code, momentum_5d, momentum_20d, momentum_60d,
                   volatility_20d, volatility_60d, atr_14d, volume_ratio_5d,
                   turnover_dev, macd_signal, adx, bb_width, rs_vs_index, obv_slope,
                   amplitude_20d, upper_shadow_ratio, ma_alignment, volume_price_corr,
                   roe, gross_margin, net_margin, debt_ratio, revenue_growth, profit_growth,
                   ocf_to_profit, accrual_ratio, goodwill_ratio,
                   pe_ttm, pb, ps_ttm, dividend_yield,
                   roa, current_ratio, peg, market_cap_pct,
                   north_flow_chg, north_days, main_net_ratio, margin_chg_rate,
                   big_order_net_ratio, consecutive_main_inflow,
                   factors_json
            FROM factor_cache
            WHERE trade_date = :trade_date
        """
        df = pd.read_sql(text(sql), self.engine, params={"trade_date": trade_date})
        if df.empty:
            return pd.DataFrame()
        df = df.set_index("stock_code")
        return df

    def _aggregate_signals(self, all_signals: list[Signal], market_state) -> list[Signal]:
        """Aggregate signals when same stock appears in multiple strategies."""
        if not all_signals:
            return []

        weights = STRATEGY_WEIGHTS[market_state]

        by_stock = defaultdict(list)
        for sig in all_signals:
            by_stock[sig.stock_code].append(sig)

        aggregated = []
        for stock_code, sigs in by_stock.items():
            if len(sigs) == 1:
                aggregated.append(sigs[0])
            else:
                total_weight = sum(weights.get(sig.strategy, 0) for sig in sigs)
                if total_weight == 0:
                    continue

                merged_direction = sum(sig.direction * weights.get(sig.strategy, 0) for sig in sigs) / total_weight
                merged_confidence = sum(sig.confidence * weights.get(sig.strategy, 0) for sig in sigs) / total_weight
                merged_holding_period = max(sig.holding_period for sig in sigs)

                merged_factors = {}
                for sig in sigs:
                    merged_factors.update(sig.factors)

                merged_sig = Signal(
                    trade_date=sigs[0].trade_date,
                    stock_code=stock_code,
                    strategy="multi",
                    direction=merged_direction,
                    confidence=merged_confidence,
                    holding_period=merged_holding_period,
                    entry_price=0.0,
                    stop_loss=0.0,
                    take_profit=0.0,
                    factors=merged_factors
                )
                aggregated.append(merged_sig)

        return aggregated

    def _adjust_confidence_by_ic(self, signals: list[Signal], factor_df: pd.DataFrame) -> list[Signal]:
        """Adjust signal confidence using IC/IR-weighted composite alpha score.

        Stocks that score well on historically predictive factors get higher confidence,
        which translates to larger position sizes via the position sizer.
        """
        if factor_df.empty or not signals:
            return signals

        # Build zscore DataFrame from factors_json if available, else use raw columns
        zscore_data = {}
        if "factors_json" in factor_df.columns:
            for code in factor_df.index:
                fj = factor_df.at[code, "factors_json"]
                if isinstance(fj, dict) and "zscore" in fj:
                    zscore_data[code] = fj["zscore"]

        if zscore_data:
            zscore_df = pd.DataFrame.from_dict(zscore_data, orient="index")
        else:
            # Fallback: compute cross-sectional z-scores from raw columns
            available = [c for c in IC_WEIGHTS if c in factor_df.columns]
            if not available:
                return signals
            zscore_df = factor_df[available].apply(lambda s: (s - s.mean()) / s.std().replace(0, np.nan))

        for sig in signals:
            if sig.stock_code not in zscore_df.index:
                continue

            row = zscore_df.loc[sig.stock_code]
            weighted_sum = 0.0
            total_abs_weight = 0.0

            for factor_name, ic_weight in IC_WEIGHTS.items():
                if factor_name in row.index:
                    val = row[factor_name]
                    if pd.notna(val):
                        # Multiply factor zscore by IC weight (sign encodes direction)
                        weighted_sum += float(val) * ic_weight
                        total_abs_weight += abs(ic_weight)

            if total_abs_weight > 0:
                composite_score = weighted_sum / total_abs_weight  # normalized to ~[-1, 1]
                adjustment = composite_score * 0.1  # ±10% confidence adjustment
                sig.confidence = float(np.clip(sig.confidence + adjustment, 0.3, 0.95))

        return signals

    def run(self, trade_date: date, stock_codes: list[str] = None) -> int:
        """Generate signals for the given date. Returns number of signals written."""
        logger.info(f"Starting signal generation for {trade_date}")

        market_state = self.detector.detect(trade_date)
        weights = STRATEGY_WEIGHTS[market_state]
        logger.info(f"Market state: {market_state.value}, weights: value={weights['value']}, growth={weights['growth']}, momentum={weights['momentum']}")

        factor_df = self._load_factor_df(trade_date)
        if factor_df.empty:
            logger.warning(f"No factor data for {trade_date}, skipping")
            return 0

        if stock_codes:
            factor_df = factor_df[factor_df.index.isin(stock_codes)]

        logger.info(f"Loaded factors for {len(factor_df)} stocks")

        all_signals = []
        for name, strategy in self.strategies.items():
            if weights.get(name, 0) == 0:
                logger.info(f"Skipping {name} strategy (zero weight in {market_state.value})")
                continue

            signals = strategy.generate(trade_date, factor_df)
            logger.info(f"{name} strategy: {len(signals)} signals")
            all_signals.extend(signals)

        if not all_signals:
            logger.warning("No signals generated")
            return 0

        aggregated = self._aggregate_signals(all_signals, market_state)
        # Filter out net-negative signals (e.g. stock only has lock_up/earnings_miss events)
        aggregated = [s for s in aggregated if s.direction > 0]
        logger.info(f"Aggregated to {len(aggregated)} final signals")

        from trading_system.db.engine import session_scope
        with session_scope() as session:
            count = write_signals(session, aggregated)

        logger.info(f"Signal generation complete for {trade_date}: {count} signals written")
        return count
