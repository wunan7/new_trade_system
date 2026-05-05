from datetime import date
import numpy as np
import pandas as pd
from trading_system.strategies.base import BaseStrategy, Signal


class MomentumStrategy(BaseStrategy):
    """Momentum strategy: ride strong trends with volume confirmation."""

    def generate(self, trade_date: date, factor_df: pd.DataFrame) -> list[Signal]:
        if factor_df.empty:
            return []

        df = factor_df.copy()

        # Compute percentiles
        df["mom20_pct"] = df["momentum_20d"].rank(pct=True)
        df["mom60_pct"] = df["momentum_60d"].rank(pct=True)

        # Apply filters
        mask = (
            (df["mom20_pct"] >= 0.50) &
            (df["mom60_pct"] >= 0.50) &
            (df["momentum_20d"] <= 0.5) &
            (df["volume_ratio_5d"] >= 0.5)
        )
        candidates = df[mask].copy()

        if candidates.empty:
            return []

        # Score
        candidates["score"] = (
            0.35 * candidates["mom20_pct"] +
            0.25 * candidates["mom60_pct"] +
            0.20 * np.clip((candidates["volume_ratio_5d"] - 0.5) / 2.5, 0, 1) +
            0.20 * np.clip(candidates["adx"], 0, 60) / 60
        )

        # Normalize score to [0, 1] within candidates
        score_min = candidates["score"].min()
        score_max = candidates["score"].max()
        if score_max > score_min:
            candidates["score_norm"] = (candidates["score"] - score_min) / (score_max - score_min)
        else:
            candidates["score_norm"] = 0.5

        # Direction
        candidates["direction"] = 0.3 + 0.7 * candidates["score_norm"]

        # Confidence
        candidates["confidence"] = 0.5
        candidates.loc[candidates["obv_slope"] > 0, "confidence"] += 0.1
        candidates.loc[candidates["obv_slope"] <= 0, "confidence"] -= 0.1

        # Top 15
        top = candidates.nlargest(15, "score")

        # Build signals
        signals = []
        for code, row in top.iterrows():
            sig = Signal(
                trade_date=trade_date,
                stock_code=code,
                strategy="momentum",
                direction=float(row["direction"]),
                confidence=float(row["confidence"]),
                holding_period=10,
                entry_price=0.0,
                stop_loss=0.0,
                take_profit=0.0,
                factors={
                    "momentum_20d": float(row["momentum_20d"]),
                    "momentum_60d": float(row["momentum_60d"]),
                    "volume_ratio_5d": float(row["volume_ratio_5d"]),
                    "adx": float(row["adx"]),
                }
            )
            signals.append(sig)

        return signals
