"""Event-driven strategy based on multiple corporate event types."""
from datetime import date, timedelta
import re
import pandas as pd
from sqlalchemy import text
from loguru import logger

from trading_system.strategies.base import Signal


# Event type configurations
EVENT_CONFIG = {
    "龙虎榜": {"lookback": 5, "holding": 7, "direction": 1.0,
               "min_count": 2, "base_confidence": 0.55, "max_signals": 10},
    "earnings_beat": {"lookback": 7, "holding": 10, "direction": 1.0,
                      "min_count": 1, "base_confidence": 0.60, "max_signals": 5},
    "buyback": {"lookback": 10, "holding": 15, "direction": 1.0,
                "min_count": 1, "base_confidence": 0.55, "max_signals": 5},
    "lock_up_expire": {"lookback": 60, "holding": 10, "direction": -1.0,
                       "min_count": 1, "base_confidence": 0.40, "max_signals": 5},
    "earnings_miss": {"lookback": 30, "holding": 5, "direction": -1.0,
                      "min_count": 1, "base_confidence": 0.45, "max_signals": 5},
}


class EventDrivenStrategy:
    """Event-driven strategy: capture short-term opportunities from corporate events.

    Handles 5 event types:
    - 龙虎榜: Dragon-Tiger List (institutional buying)
    - earnings_beat: Earnings surprise (positive)
    - buyback: Share repurchase plan
    - lock_up_expire: Restricted share unlock (negative signal, used as filter)
    - earnings_miss: Earnings disappointment (negative signal, used as filter)
    """

    def __init__(self, db_engine):
        self.engine = db_engine
        self.min_net_buy = 5_000_000  # 500万元 for 龙虎榜 (data stored in yuan)

    def generate(self, trade_date: date, factor_df: pd.DataFrame) -> list[Signal]:
        """Generate signals from all event types.

        Only positive events generate buy signals.
        Negative events (earnings_miss, lock_up_expire) are NOT included as signals —
        they are too disruptive when mixed with other strategies in aggregation.
        Instead, they should be consumed as filters externally if needed.
        """
        all_signals = []

        # Positive events → generate buy signals
        all_signals.extend(self._handle_lhb(trade_date))
        all_signals.extend(self._handle_earnings_beat(trade_date))
        all_signals.extend(self._handle_buyback(trade_date))

        logger.info(f"Event strategy generated {len(all_signals)} signals")
        return all_signals

    def _query_events(self, event_type: str, trade_date: date) -> list:
        """Query events table for a given type within lookback window."""
        config = EVENT_CONFIG[event_type]
        start_date = trade_date - timedelta(days=config["lookback"])

        query = text("""
            SELECT code, event_date, title, content, sentiment, impact_strength
            FROM events
            WHERE event_type = :etype
              AND event_date BETWEEN :start_date AND :end_date
            ORDER BY event_date DESC
        """)

        with self.engine.connect() as conn:
            result = conn.execute(query, {
                "etype": event_type,
                "start_date": start_date,
                "end_date": trade_date,
            })
            return result.fetchall()

    # ─── 龙虎榜 (Dragon-Tiger List) ───

    def _handle_lhb(self, trade_date: date) -> list[Signal]:
        """Handle 龙虎榜 events: institutional buying signals."""
        rows = self._query_events("龙虎榜", trade_date)
        if not rows:
            return []

        records = []
        for code, event_date, title, content, sentiment, impact in rows:
            match = re.search(r'净买入:\s*([-\d.]+)万元', content or "")
            if match:
                net_buy = float(match.group(1))
                if net_buy > self.min_net_buy:
                    records.append({"code": code, "event_date": event_date,
                                    "net_buy": net_buy, "reason": title})

        if not records:
            return []

        df = pd.DataFrame(records)
        appearance_count = df.groupby("code").size()

        signals = []
        for code, count in appearance_count.items():
            if count < EVENT_CONFIG["龙虎榜"]["min_count"]:
                continue
            stock_lhb = df[df["code"] == code].sort_values("event_date", ascending=False).iloc[0]
            confidence = min(0.5 + count * 0.1 + float(stock_lhb["net_buy"]) / 1e8 * 0.05, 0.95)
            signals.append(self._make_signal(
                trade_date, code, "龙虎榜", confidence,
                {"net_buy": float(stock_lhb["net_buy"]), "appearances": int(count),
                 "reason": str(stock_lhb["reason"])}
            ))
        return signals

    # ─── 业绩超预期 (Earnings Beat) ───

    def _handle_earnings_beat(self, trade_date: date) -> list[Signal]:
        """Handle earnings_beat: positive earnings surprise."""
        rows = self._query_events("earnings_beat", trade_date)
        if not rows:
            return []

        signals = []
        seen_codes = set()
        for code, event_date, title, content, sentiment, impact in rows:
            if code in seen_codes:
                continue
            seen_codes.add(code)

            # Parse beat magnitude
            match = re.search(r'变动幅度:\s*\+([\d.]+)%', content or "")
            beat_pct = float(match.group(1)) if match else 10.0

            # Higher beat → higher confidence
            confidence = min(0.55 + beat_pct / 200 * 0.3, 0.90)

            # Impact strength boost
            if impact == "high":
                confidence = min(confidence + 0.1, 0.95)

            signals.append(self._make_signal(
                trade_date, code, "earnings_beat", confidence,
                {"beat_pct": beat_pct, "impact": impact or "medium", "reason": title}
            ))
        # Keep top N by confidence
        signals.sort(key=lambda s: s.confidence, reverse=True)
        return signals[:EVENT_CONFIG["earnings_beat"]["max_signals"]]

    # ─── 公司回购 (Buyback) ───

    def _handle_buyback(self, trade_date: date) -> list[Signal]:
        """Handle buyback: share repurchase plans signal management confidence."""
        rows = self._query_events("buyback", trade_date)
        if not rows:
            return []

        signals = []
        seen_codes = set()
        for code, event_date, title, content, sentiment, impact in rows:
            if code in seen_codes:
                continue
            seen_codes.add(code)

            # Parse buyback amount
            match = re.search(r'回购金额:\s*([\d.]+)万元', content or "")
            amount = float(match.group(1)) if match else 0

            confidence = 0.50
            if amount > 10000:  # > 1亿
                confidence = 0.65
            elif amount > 5000:  # > 5000万
                confidence = 0.60

            if float(sentiment or 0) > 0.5:
                confidence = min(confidence + 0.05, 0.90)

            signals.append(self._make_signal(
                trade_date, code, "buyback", confidence,
                {"buyback_amount": amount, "impact": impact or "low", "reason": title}
            ))
        signals.sort(key=lambda s: s.confidence, reverse=True)
        return signals[:EVENT_CONFIG["buyback"]["max_signals"]]

    # ─── 限售解禁 (Lock-up Expire) — 负面信号 ───

    def _handle_lock_up(self, trade_date: date) -> list[Signal]:
        """Handle lock_up_expire: negative signal (selling pressure)."""
        rows = self._query_events("lock_up_expire", trade_date)
        if not rows:
            return []

        signals = []
        seen_codes = set()
        for code, event_date, title, content, sentiment, impact in rows:
            if code in seen_codes:
                continue
            seen_codes.add(code)

            # Parse unlock ratio
            match = re.search(r'占流通盘:\s*([\d.]+)%', content or "")
            unlock_pct = float(match.group(1)) if match else 0

            # Only generate negative signal for large unlocks (> 1% of float)
            if unlock_pct < 1.0:
                continue

            confidence = min(0.40 + unlock_pct / 20 * 0.3, 0.80)

            signals.append(self._make_signal(
                trade_date, code, "lock_up_expire", confidence,
                {"unlock_pct": unlock_pct, "impact": impact or "low", "reason": title},
                direction=-0.5  # Negative signal
            ))
        return signals

    # ─── 业绩不及预期 (Earnings Miss) — 负面信号 ───

    def _handle_earnings_miss(self, trade_date: date) -> list[Signal]:
        """Handle earnings_miss: negative earnings surprise."""
        rows = self._query_events("earnings_miss", trade_date)
        if not rows:
            return []

        signals = []
        seen_codes = set()
        for code, event_date, title, content, sentiment, impact in rows:
            if code in seen_codes:
                continue
            seen_codes.add(code)

            match = re.search(r'变动幅度:\s*(-[\d.]+)%', content or "")
            miss_pct = abs(float(match.group(1))) if match else 10.0

            confidence = min(0.45 + miss_pct / 100 * 0.3, 0.85)

            if impact == "high":
                confidence = min(confidence + 0.1, 0.90)

            signals.append(self._make_signal(
                trade_date, code, "earnings_miss", confidence,
                {"miss_pct": miss_pct, "impact": impact or "medium", "reason": title},
                direction=-0.5  # Negative signal
            ))
        return signals

    # ─── Helper ───

    def _make_signal(self, trade_date, code, event_type, confidence,
                     factors_dict, direction=None):
        """Create a Signal object with event-specific parameters."""
        config = EVENT_CONFIG[event_type]
        return Signal(
            trade_date=trade_date,
            stock_code=code,
            direction=direction if direction is not None else config["direction"],
            confidence=confidence,
            holding_period=config["holding"],
            entry_price=None,
            stop_loss=None,
            take_profit=None,
            factors=factors_dict,
            strategy="event",
        )
