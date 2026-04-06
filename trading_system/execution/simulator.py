"""Trade simulation engine: convert PositionOrders to executed trades."""
from datetime import date

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from trading_system.db.models import PortfolioPosition, TradeLog, PortfolioNav
from trading_system.execution.cost_model import calc_trade_cost
from trading_system.execution.portfolio import Portfolio, PositionRecord
from trading_system.risk.position_sizer import PositionOrder


class TradeSimulator:
    """Simulate trade execution with realistic cost model."""

    def execute_buys(self, orders: list[PositionOrder], portfolio: Portfolio,
                     trade_date: date, session: Session) -> list[dict]:
        """Execute buy orders: update portfolio + write to DB.

        Returns list of trade_log dicts.
        """
        trades = []
        for order in orders:
            sig = order.signal
            code = sig.stock_code

            # Skip if already holding
            if code in portfolio.positions:
                continue

            # Check cash sufficiency
            amount = sig.entry_price * order.shares
            cost_info = calc_trade_cost(sig.entry_price, order.shares, "BUY")
            total_cost = amount + cost_info["total"]

            if total_cost > portfolio.cash:
                logger.warning(f"Insufficient cash for {code}: need {total_cost:,.0f}, have {portfolio.cash:,.0f}")
                continue

            # Create position record
            pos = PositionRecord(
                code=code,
                open_date=trade_date,
                open_price=sig.entry_price,
                shares=order.shares,
                strategy=sig.strategy,
                signal_id=None,
                stop_loss_price=sig.stop_loss,
                take_profit_price=sig.take_profit,
                max_hold_days=sig.holding_period,
                max_price=sig.entry_price,
                current_price=sig.entry_price,
            )

            # Write to portfolio_positions
            db_pos = PortfolioPosition(
                code=code, open_date=trade_date, open_price=sig.entry_price,
                current_price=sig.entry_price, position_pct=order.actual_pct,
                shares=order.shares, strategy_source=sig.strategy,
                stop_loss_price=sig.stop_loss, take_profit_price=sig.take_profit,
                max_hold_days=sig.holding_period, status="open",
            )
            session.add(db_pos)
            session.flush()  # get id
            pos.position_id = db_pos.id

            # Update portfolio in memory
            portfolio.add_position(pos, cost_info["total"])

            # Write trade log
            trade = TradeLog(
                trade_date=trade_date, code=code, direction="BUY",
                price=sig.entry_price, shares=order.shares,
                amount=amount, strategy=sig.strategy,
                position_id=db_pos.id,
                commission=cost_info["commission"],
                stamp_tax=cost_info["stamp_tax"],
                slippage=cost_info["slippage"],
                is_paper=True,
            )
            session.add(trade)
            trades.append({
                "code": code, "direction": "BUY", "shares": order.shares,
                "price": sig.entry_price, "cost": cost_info["total"],
            })

        logger.info(f"Executed {len(trades)} buy trades")
        return trades

    def execute_sells(self, exits: list[tuple[str, str, float]],
                      portfolio: Portfolio, trade_date: date,
                      session: Session) -> list[dict]:
        """Execute sell orders for positions that triggered exit.

        Args:
            exits: list of (code, reason, sell_price)
            portfolio: current portfolio state
            trade_date: trade date
            session: DB session

        Returns list of trade_log dicts.
        """
        trades = []
        for code, reason, sell_price in exits:
            pos = portfolio.positions.get(code)
            if pos is None:
                continue

            cost_info = calc_trade_cost(sell_price, pos.shares, "SELL")
            amount = sell_price * pos.shares
            pnl_pct = (sell_price - pos.open_price) / pos.open_price

            # Update portfolio_positions: close
            if pos.position_id:
                session.execute(text("""
                    UPDATE portfolio_positions
                    SET status = 'closed', close_date = :cd, close_price = :cp,
                        close_reason = :reason, pnl_pct = :pnl, updated_at = NOW()
                    WHERE id = :pid
                """), {"cd": trade_date, "cp": sell_price, "reason": reason,
                       "pnl": round(pnl_pct, 4), "pid": pos.position_id})

            # Write trade log
            trade = TradeLog(
                trade_date=trade_date, code=code, direction="SELL",
                price=sell_price, shares=pos.shares,
                amount=amount, strategy=pos.strategy,
                position_id=pos.position_id,
                commission=cost_info["commission"],
                stamp_tax=cost_info["stamp_tax"],
                slippage=cost_info["slippage"],
                is_paper=True,
            )
            session.add(trade)

            # Update portfolio in memory
            portfolio.close_position(code, sell_price, cost_info["total"])

            trades.append({
                "code": code, "direction": "SELL", "shares": pos.shares,
                "price": sell_price, "reason": reason,
                "pnl_pct": round(pnl_pct * 100, 2),
                "cost": cost_info["total"],
            })

        logger.info(f"Executed {len(trades)} sell trades")
        return trades

    def update_nav(self, portfolio: Portfolio, trade_date: date,
                   benchmark_return: float, session: Session,
                   prev_nav: float = None):
        """Write daily portfolio NAV record."""
        total_value = portfolio.get_total_value_estimate()
        positions_value = total_value - portfolio.cash

        if prev_nav and prev_nav > 0:
            daily_return = (total_value - prev_nav) / prev_nav
        else:
            daily_return = 0.0

        cumulative_return = (total_value - portfolio.total_capital) / portfolio.total_capital

        # Upsert NAV
        existing = session.execute(text(
            "SELECT 1 FROM portfolio_nav WHERE nav_date = :d"
        ), {"d": trade_date}).fetchone()

        if existing:
            session.execute(text("""
                UPDATE portfolio_nav SET
                    total_value = :tv, cash = :cash, positions_value = :pv,
                    position_count = :pc, daily_return = :dr,
                    cumulative_return = :cr, benchmark_return = :br,
                    excess_return = :er, is_paper = true, updated_at = NOW()
                WHERE nav_date = :d
            """), {
                "tv": round(total_value, 2), "cash": round(portfolio.cash, 2),
                "pv": round(positions_value, 2), "pc": len(portfolio.positions),
                "dr": round(daily_return, 6), "cr": round(cumulative_return, 6),
                "br": round(benchmark_return, 6),
                "er": round(daily_return - benchmark_return, 6),
                "d": trade_date,
            })
        else:
            nav = PortfolioNav(
                nav_date=trade_date,
                total_value=round(total_value, 2),
                cash=round(portfolio.cash, 2),
                positions_value=round(positions_value, 2),
                position_count=len(portfolio.positions),
                daily_return=round(daily_return, 6),
                cumulative_return=round(cumulative_return, 6),
                benchmark_return=round(benchmark_return, 6),
                excess_return=round(daily_return - benchmark_return, 6),
                is_paper=True,
            )
            session.add(nav)

        logger.info(f"NAV {trade_date}: {total_value:,.0f} (daily={daily_return:+.2%})")
