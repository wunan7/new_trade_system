"""Portfolio state management: positions, cash, value tracking."""
from datetime import date
from dataclasses import dataclass, field

from loguru import logger
from sqlalchemy import text


@dataclass
class PositionRecord:
    """In-memory representation of an open position."""
    code: str
    open_date: date
    open_price: float
    shares: int
    strategy: str
    signal_id: int | None
    stop_loss_price: float
    take_profit_price: float
    max_hold_days: int
    max_price: float          # highest price since entry (for trailing stop)
    current_price: float = 0.0
    industry: str = ""
    position_id: int | None = None   # DB id


class Portfolio:
    """Manage portfolio state: cash, positions, and valuation."""

    def __init__(self, total_capital: float = 1_000_000):
        self.total_capital = total_capital
        self.cash = total_capital
        self.positions: dict[str, PositionRecord] = {}  # code -> PositionRecord
        self._industry_map: dict[str, str] = {}         # code -> industry

    def load_from_db(self, engine, trade_date: date = None):
        """Load open positions from portfolio_positions table."""
        sql = "SELECT id, code, open_date, open_price, shares, strategy_source, " \
              "signal_id, stop_loss_price, take_profit_price, max_hold_days, current_price " \
              "FROM portfolio_positions WHERE status = 'open'"
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            for row in result:
                pos = PositionRecord(
                    code=row[1], open_date=row[2], open_price=float(row[3]),
                    shares=row[4], strategy=row[5], signal_id=row[6],
                    stop_loss_price=float(row[7]) if row[7] else 0,
                    take_profit_price=float(row[8]) if row[8] else 0,
                    max_hold_days=row[9] or 60,
                    max_price=float(row[10]) if row[10] else float(row[3]),
                    current_price=float(row[10]) if row[10] else float(row[3]),
                    position_id=row[0],
                )
                self.positions[pos.code] = pos

            # Load industry mapping
            if self.positions:
                codes = tuple(self.positions.keys())
                r = conn.execute(text(
                    "SELECT code, industry_l1 FROM stock_info WHERE code IN :codes"
                ), {"codes": codes})
                for row in r:
                    self._industry_map[row[0]] = row[1] or ""
                    if row[0] in self.positions:
                        self.positions[row[0]].industry = row[1] or ""

            # Compute cash from total_capital - positions value
            positions_value = sum(p.current_price * p.shares for p in self.positions.values())

            # Load last NAV to get accurate cash
            r = conn.execute(text(
                "SELECT cash FROM portfolio_nav ORDER BY nav_date DESC LIMIT 1"
            ))
            row = r.fetchone()
            if row and row[0] is not None:
                self.cash = float(row[0])
            else:
                self.cash = self.total_capital - positions_value

        logger.info(f"Portfolio loaded: {len(self.positions)} positions, cash={self.cash:,.0f}")

    def update_prices(self, prices: dict[str, float]):
        """Update current prices and max prices for all positions."""
        for code, pos in self.positions.items():
            if code in prices:
                pos.current_price = prices[code]
                pos.max_price = max(pos.max_price, prices[code])

    def get_position_pct(self, code: str) -> float:
        """Get current position weight for a stock."""
        total = self.get_total_value_estimate()
        if total <= 0 or code not in self.positions:
            return 0.0
        pos = self.positions[code]
        return (pos.current_price * pos.shares) / total

    def get_industry_pct(self, industry: str) -> float:
        """Get total position weight for an industry."""
        total = self.get_total_value_estimate()
        if total <= 0:
            return 0.0
        industry_value = sum(
            p.current_price * p.shares
            for p in self.positions.values()
            if p.industry == industry
        )
        return industry_value / total

    def get_total_position_pct(self) -> float:
        """Get total portfolio position ratio (1 - cash ratio)."""
        total = self.get_total_value_estimate()
        if total <= 0:
            return 0.0
        return 1.0 - (self.cash / total)

    def get_total_value_estimate(self) -> float:
        """Get total portfolio value (cash + positions market value)."""
        positions_value = sum(
            p.current_price * p.shares for p in self.positions.values()
        )
        return self.cash + positions_value

    def add_position(self, pos: PositionRecord, cost: float):
        """Add a new position, deduct cash by amount + cost."""
        self.positions[pos.code] = pos
        self._industry_map[pos.code] = pos.industry
        self.cash -= (pos.open_price * pos.shares + cost)

    def close_position(self, code: str, sell_price: float, cost: float):
        """Close a position, add proceeds - cost to cash."""
        if code not in self.positions:
            return
        pos = self.positions.pop(code)
        self.cash += (sell_price * pos.shares - cost)
