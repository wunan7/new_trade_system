from datetime import date
import numpy as np
import pandas as pd
from trading_system.strategies.base import BaseStrategy, Signal


class GrowthStrategy(BaseStrategy):
    """Growth investing strategy: high earnings/revenue growth + quality."""

    def generate(self, trade_date: date, factor_df: pd.DataFrame) -> list[Signal]:
        if factor_df.empty:
            return []

        df = factor_df.copy()

        # Apply filters
        mask = (
            (df["profit_growth"] > 30) &
            (df["revenue_growth"] > 20) &
            (df["roe"] > 8)
        )
        candidates = df[mask].copy()

        if candidates.empty:
            return []

        # Score
        candidates["score"] = (
            0.40 * np.clip(candidates["profit_growth"], 0, 200) / 200 +
            0.30 * np.clip(candidates["revenue_growth"], 0, 100) / 100 +
            0.20 * np.clip(candidates["roe"], 0, 50) / 50 +
            0.10 * np.clip(candidates["gross_margin"], 0, 80) / 80
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
        candidates.loc[candidates["net_margin"] > 15, "confidence"] += 0.1
        candidates.loc[candidates["revenue_growth"] > 40, "confidence"] += 0.1

        # Top 20
        top = candidates.nlargest(20, "score")

        # Build signals
        signals = []
        for code, row in top.iterrows():
            sig = Signal(
                trade_date=trade_date,
                stock_code=code,
                strategy="growth",
                direction=float(row["direction"]),
                confidence=float(row["confidence"]),
                holding_period=60,
                entry_price=0.0,
                stop_loss=0.0,
                take_profit=0.0,
                factors={
                    "profit_growth": float(row["profit_growth"]),
                    "revenue_growth": float(row["revenue_growth"]),
                    "roe": float(row["roe"]),
                    "gross_margin": float(row["gross_margin"]),
                }
            )
            signals.append(sig)

        return signals
