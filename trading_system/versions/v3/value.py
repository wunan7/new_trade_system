from datetime import date
import numpy as np
import pandas as pd
from trading_system.strategies.base import BaseStrategy, Signal


class ValueStrategy(BaseStrategy):
    """Value investing strategy: low valuation + quality + income."""

    def generate(self, trade_date: date, factor_df: pd.DataFrame) -> list[Signal]:
        if factor_df.empty:
            return []

        df = factor_df.copy()

        # Apply quality/income/leverage filters first
        mask = (
            (df["roe"] > 12) &
            (df["dividend_yield"] >= 0.02) &
            (df["debt_ratio"] < 60)
        )
        candidates = df[mask].copy()

        if candidates.empty:
            return []

        # Compute pb percentile within candidates (relative value ranking)
        n = len(candidates)
        if n > 1:
            candidates["pb_pct"] = (candidates["pb"].rank(method="min") - 1) / (n - 1)
        else:
            candidates["pb_pct"] = 0.0

        # Further filter: keep only bottom 30% pb (most undervalued) when universe is large enough
        if n >= 10:
            candidates = candidates[candidates["pb_pct"] < 0.30].copy()
            if candidates.empty:
                return []

        # Score
        candidates["score"] = (
            0.30 * (1 - candidates["pb_pct"]) +
            0.30 * np.clip(candidates["roe"], 0, 50) / 50 +
            0.20 * np.clip(candidates["dividend_yield"], 0, 0.10) / 0.10 +
            0.20 * np.clip(candidates["ocf_to_profit"], 0, 3) / 3
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
        candidates.loc[candidates["goodwill_ratio"] < 0.1, "confidence"] += 0.1
        candidates.loc[candidates["accrual_ratio"] < 0, "confidence"] += 0.1

        # Top 20
        top = candidates.nlargest(20, "score")

        # Build signals
        signals = []
        for code, row in top.iterrows():
            sig = Signal(
                trade_date=trade_date,
                stock_code=code,
                strategy="value",
                direction=float(row["direction"]),
                confidence=float(row["confidence"]),
                holding_period=60,
                entry_price=0.0,  # Placeholder (Layer 4 fills this)
                stop_loss=0.0,
                take_profit=0.0,
                factors={
                    "pb": float(row["pb"]),
                    "roe": float(row["roe"]),
                    "dividend_yield": float(row["dividend_yield"]),
                    "debt_ratio": float(row["debt_ratio"]),
                    "ocf_to_profit": float(row["ocf_to_profit"]),
                }
            )
            signals.append(sig)

        return signals
