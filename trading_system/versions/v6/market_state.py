"""Market state detection from CSI300 index data."""
import numpy as np
import pandas as pd
from loguru import logger

from trading_system.pipeline.data_loader import FactorDataLoader
from trading_system.strategies.base import MarketState, STRATEGY_WEIGHTS


class MarketStateDetector:
    """Detects market regime from CSI300 index data.

    Classifies each trading date into one of six MarketState values by
    combining a trend signal (price vs MA60 + 20-day momentum) with a
    volatility signal (20-day vs 60-day realised vol).
    """

    def __init__(self, engine=None):
        if engine is None:
            from trading_system.db.engine import get_engine
            engine = get_engine()
        self.loader = FactorDataLoader(engine, lookback_days=120)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, trade_date) -> MarketState:
        """Detect market state for the given date using 6 dimensions.

        Dimensions:
        1. Trend: price vs MA60 + momentum
        2. Volatility: 20d vs 60d realized vol
        3. Market breadth: % of stocks above MA20
        4. Northbound flow: cumulative net inflow trend
        5. Turnover: current vs historical percentile
        6. Limit ratio: (up_limit - down_limit) / total

        Returns one of the six MarketState enum values.
        Falls back to NEUTRAL_LOW when there is insufficient data.
        """
        index_df = self.loader.load_index_prices(trade_date, index_code="000300")

        if len(index_df) < 60:
            logger.warning(
                f"Insufficient index data ({len(index_df)} days), "
                "defaulting to NEUTRAL_LOW"
            )
            return MarketState.NEUTRAL_LOW

        close = index_df["close"]

        # ---- 1. Trend detection ----------------------------------------
        ma60 = close.rolling(60).mean().iloc[-1]
        current_close = close.iloc[-1]
        pct_above_ma60 = (current_close - ma60) / ma60

        momentum_20d = (
            (close.iloc[-1] / close.iloc[-20] - 1) if len(close) >= 20 else 0.0
        )

        trend_score = 0
        if pct_above_ma60 > 0.02 and momentum_20d > 0:
            trend_score = 2  # Strong bull
        elif pct_above_ma60 > 0:
            trend_score = 1  # Weak bull
        elif pct_above_ma60 < -0.02 and momentum_20d < 0:
            trend_score = -2  # Strong bear
        elif pct_above_ma60 < 0:
            trend_score = -1  # Weak bear

        # ---- 2. Volatility detection ------------------------------------
        returns = close.pct_change().dropna()
        vol_20d = (
            returns.tail(20).std() * np.sqrt(252) if len(returns) >= 20 else 0.0
        )
        vol_60d = (
            returns.tail(60).std() * np.sqrt(252) if len(returns) >= 60 else vol_20d
        )

        vol_score = 0
        if vol_60d > 0 and vol_20d > vol_60d * 1.2:
            vol_score = 1  # High volatility

        # ---- 3. Market breadth (% stocks above MA20) --------------------
        breadth_score = self._calc_market_breadth(trade_date)

        # ---- 4. Northbound flow trend -----------------------------------
        north_score = self._calc_northbound_trend(trade_date)

        # ---- 5. Turnover percentile -------------------------------------
        turnover_score = self._calc_turnover_percentile(trade_date, index_df)

        # ---- 6. Limit ratio (up_limit - down_limit) / total -------------
        limit_score = self._calc_limit_ratio(trade_date)

        # ---- Combine all dimensions -------------------------------------
        # Trend + breadth + north → overall trend (BULL/NEUTRAL/BEAR)
        combined_trend_score = trend_score + breadth_score + north_score
        if combined_trend_score >= 3:
            trend = "BULL"
        elif combined_trend_score <= -3:
            trend = "BEAR"
        else:
            trend = "NEUTRAL"

        # Volatility + turnover + limit → overall volatility (HIGH/LOW)
        # Increase threshold to reduce sensitivity
        combined_vol_score = vol_score + turnover_score + limit_score
        if combined_vol_score >= 2:  # Keep at 2 (already conservative)
            volatility = "HIGH"
        else:
            volatility = "LOW"

        # ---- Combine -------------------------------------------------
        state_name = f"{trend}_{volatility}"
        state = MarketState(state_name.lower())

        logger.info(
            f"Market state on {trade_date}: {state.value} "
            f"(trend_score={combined_trend_score}, vol_score={combined_vol_score}, "
            f"close={current_close:.2f}, MA60={ma60:.2f})"
        )
        return state

    def _calc_market_breadth(self, trade_date) -> int:
        """Calculate market breadth: % of stocks above MA20.

        Returns: +1 if > 60%, -1 if < 40%, 0 otherwise
        """
        from sqlalchemy import text

        # Simplified: use momentum_20d as proxy for "above MA20"
        sql = text("""
            SELECT COUNT(*) FILTER (WHERE momentum_20d > 0) * 100.0 / COUNT(*) AS pct_positive
            FROM factor_cache
            WHERE trade_date = :trade_date
              AND momentum_20d IS NOT NULL
        """)
        with self.loader.engine.connect() as conn:
            result = conn.execute(sql, {"trade_date": trade_date})
            row = result.fetchone()
            pct = row[0] if row and row[0] else 50.0

        if pct > 60:
            return 1
        elif pct < 40:
            return -1
        return 0

    def _calc_northbound_trend(self, trade_date) -> int:
        """Calculate northbound flow trend: cumulative net inflow past 5 days.

        Returns: +1 if positive, -1 if negative, 0 if no data
        """
        from sqlalchemy import text
        from datetime import timedelta
        start_date = trade_date - timedelta(days=5)

        sql = text("""
            SELECT SUM(north_net_buy) AS cumulative_flow
            FROM money_flow
            WHERE trade_date <= :trade_date
              AND trade_date >= :start_date
        """)
        with self.loader.engine.connect() as conn:
            result = conn.execute(sql, {"trade_date": trade_date, "start_date": start_date})
            row = result.fetchone()
            flow = row[0] if row and row[0] else 0

        if flow > 0:
            return 1
        elif flow < 0:
            return -1
        return 0

    def _calc_turnover_percentile(self, trade_date, index_df: pd.DataFrame) -> int:
        """Calculate turnover percentile: current vs past 60 days.

        Returns: +1 if > 80th percentile, 0 otherwise
        """
        if "turnover" not in index_df.columns or len(index_df) < 60:
            return 0

        turnover = index_df["turnover"].tail(60)
        current_turnover = turnover.iloc[-1]
        percentile = (turnover < current_turnover).sum() / len(turnover)

        if percentile > 0.8:
            return 1
        return 0

    def _calc_limit_ratio(self, trade_date) -> int:
        """Calculate limit ratio: (up_limit - down_limit) / total stocks.

        Returns: +1 if > 5%, -1 if < -5%, 0 otherwise
        """
        from sqlalchemy import text
        sql = text("""
            SELECT
                COUNT(*) FILTER (WHERE pct_change >= 9.9) AS up_limit,
                COUNT(*) FILTER (WHERE pct_change <= -9.9) AS down_limit,
                COUNT(*) AS total
            FROM stock_daily
            WHERE trade_date = :trade_date
        """)
        with self.loader.engine.connect() as conn:
            result = conn.execute(sql, {"trade_date": trade_date})
            row = result.fetchone()
            if not row or row[2] == 0:
                return 0
            ratio = (row[0] - row[1]) / row[2]

        if ratio > 0.05:
            return 1
        elif ratio < -0.05:
            return -1
        return 0

    def _calc_sentiment_dimension(self, trade_date) -> int:
        """TrendRadar market sentiment score.

        Returns: +1 if bullish (>0.3), -1 if bearish (<-0.3), 0 otherwise.
        Falls back to 0 if no data (TrendRadar data starts 2026-03-21).
        """
        from sqlalchemy import text, create_engine
        from datetime import timedelta
        try:
            opinion_engine = create_engine(
                "postgresql://postgres:postgres@localhost:5432/finance_public_opinion",
                pool_pre_ping=True,
            )
            # Use T-1 (sentiment generated after market close)
            t_minus_1 = (trade_date - timedelta(days=1)).isoformat()
            lookback = (trade_date - timedelta(days=7)).isoformat()
            sql = text("""
                SELECT market_sentiment_score FROM ai_analysis_results
                WHERE data_date >= :start AND data_date <= :end AND success = 1
                  AND market_sentiment_score IS NOT NULL
                ORDER BY data_date DESC, id DESC LIMIT 1
            """)
            with opinion_engine.connect() as conn:
                row = conn.execute(sql, {"start": lookback, "end": t_minus_1}).fetchone()
            if row and row[0] is not None:
                score = float(row[0])
                if score > 0.3:
                    return 1
                elif score < -0.3:
                    return -1
        except Exception:
            pass
        return 0

    def _calc_macro_dimension(self, trade_date) -> int:
        """Macro dimension: PMI manufacturing trend.

        Returns: +1 if PMI > 50 and rising, -1 if PMI < 50 and falling, 0 otherwise.
        """
        from sqlalchemy import text
        sql = text("""
            SELECT value FROM macro_data
            WHERE indicator = 'PMI_MFG' AND report_date <= :td
            ORDER BY report_date DESC LIMIT 2
        """)
        with self.loader.engine.connect() as conn:
            rows = conn.execute(sql, {"td": trade_date}).fetchall()

        if len(rows) < 2:
            return 0

        current_pmi = float(rows[0][0]) if rows[0][0] else 50
        prev_pmi = float(rows[1][0]) if rows[1][0] else 50

        if current_pmi > 50 and current_pmi > prev_pmi:
            return 1  # Expansionary and improving
        elif current_pmi < 50 and current_pmi < prev_pmi:
            return -1  # Contractionary and worsening
        return 0

    def get_weights(self, state: MarketState) -> dict:
        """Return strategy allocation weights for the given market state."""
        return STRATEGY_WEIGHTS[state]

    def get_position_limit(self, state: MarketState) -> float:
        """Return maximum gross position ratio for the given market state."""
        return STRATEGY_WEIGHTS[state]["position_limit"]
