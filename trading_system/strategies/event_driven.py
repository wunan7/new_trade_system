"""Event-driven strategy based on Dragon-Tiger List (龙虎榜)."""
from datetime import date, timedelta
import re
import pandas as pd
from sqlalchemy import text
from loguru import logger

from trading_system.strategies.base import Signal


class EventDrivenStrategy:
    """Event-driven strategy: capture short-term opportunities from Dragon-Tiger List.

    Logic:
    - Net buy amount > 5M yuan → strong buying interest
    - Appeared on list 2+ times in past 5 days → sustained interest
    - Holding period: 5-10 days (event-driven is short-term)
    """

    def __init__(self, db_engine):
        self.engine = db_engine
        self.lookback_days = 5
        self.min_net_buy = 5_000_000  # 500万元 (data in events.content is stored in yuan)

    def generate(self, trade_date: date, factor_df: pd.DataFrame) -> list[Signal]:
        """Generate signals from Dragon-Tiger List events in database."""
        start_date = trade_date - timedelta(days=self.lookback_days)

        # Query events table for recent 龙虎榜 records
        query = text("""
            SELECT code, event_date, title, content
            FROM events
            WHERE event_type = '龙虎榜'
              AND event_date BETWEEN :start_date AND :end_date
            ORDER BY event_date DESC
        """)

        with self.engine.connect() as conn:
            result = conn.execute(query, {"start_date": start_date, "end_date": trade_date})
            rows = result.fetchall()

        if not rows:
            logger.info("No lhb data in past 5 days")
            return []

        # Parse net_buy from content field: "净买入: XXX万元"
        records = []
        for code, event_date, title, content in rows:
            match = re.search(r'净买入:\s*([-\d.]+)万元', content)
            if match:
                net_buy = float(match.group(1))
                records.append({
                    'code': code,
                    'event_date': event_date,
                    'net_buy': net_buy,
                    'reason': title
                })

        if not records:
            logger.info("No parseable lhb data")
            return []

        lhb_df = pd.DataFrame(records)

        # Filter: net_buy > 5M (500万)
        lhb_df = lhb_df[lhb_df['net_buy'] > self.min_net_buy]

        if lhb_df.empty:
            logger.info("No strong net buying in lhb data")
            return []

        # Count appearances per stock
        appearance_count = lhb_df.groupby('code').size()

        # Generate signals for stocks with 2+ appearances
        signals = []
        for code, count in appearance_count.items():
            if count < 2:
                continue

            # Get latest record for this stock
            stock_lhb = lhb_df[lhb_df['code'] == code].sort_values('event_date', ascending=False).iloc[0]

            # Calculate confidence: higher for more appearances and larger net buy
            confidence = min(0.5 + count * 0.1 + float(stock_lhb['net_buy']) / 1e8 * 0.05, 0.95)

            signal = Signal(
                trade_date=trade_date,
                stock_code=code,
                direction=1.0,  # Long only
                confidence=confidence,
                holding_period=7,  # 5-10 days average
                entry_price=None,  # Will be filled by risk manager
                stop_loss=None,
                take_profit=None,
                factors={
                    'net_buy': float(stock_lhb['net_buy']),
                    'appearances': int(count),
                    'reason': str(stock_lhb['reason']),
                },
                strategy='event'
            )
            signals.append(signal)

        logger.info(f"Event strategy generated {len(signals)} signals from {len(lhb_df)} lhb records")
        return signals

