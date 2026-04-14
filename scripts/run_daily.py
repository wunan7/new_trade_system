"""Daily trading pipeline: factors → signals → risk control → execution → NAV."""
import argparse
from datetime import date, datetime, timedelta

import pandas as pd
from loguru import logger
from sqlalchemy import text

from trading_system.db.engine import get_engine, session_scope
from trading_system.pipeline.orchestrator import FactorPipeline
from trading_system.signals.generator import SignalGenerator
from trading_system.strategies.market_state import MarketStateDetector
from trading_system.risk.constraints import ConstraintFilter
from trading_system.risk.position_sizer import PositionSizer
from trading_system.risk.stop_loss import StopLossCalculator
from trading_system.risk.drawdown_monitor import DrawdownMonitor
from trading_system.execution.portfolio import Portfolio
from trading_system.execution.simulator import TradeSimulator

INITIAL_CAPITAL = 1_000_000  # 100万


def run_daily(trade_date: date, skip_factors: bool = False, skip_signals: bool = False):
    """Run full daily pipeline for one trading date."""
    engine = get_engine()

    # Step 1: Compute factors (Layer 2)
    if not skip_factors:
        logger.info("=" * 60)
        logger.info("Step 1: Computing factors")
        fp = FactorPipeline(engine)
        fp.run(trade_date)

    # Step 2: Generate signals (Layer 3)
    if not skip_signals:
        logger.info("=" * 60)
        logger.info("Step 2: Generating signals")
        sg = SignalGenerator(engine)
        sg.run(trade_date)

    # Step 3: Load portfolio state
    logger.info("=" * 60)
    logger.info("Step 3: Loading portfolio")
    portfolio = Portfolio(INITIAL_CAPITAL)
    portfolio.load_from_db(engine)

    # Load current prices for all held + candidate stocks
    prices = _load_prices(engine, trade_date)
    portfolio.update_prices(prices)

    # Step 4: Market state detection
    detector = MarketStateDetector(engine)
    market_state = detector.detect(trade_date)
    logger.info(f"Market state: {market_state.value}")

    # Step 5: Drawdown check
    dd_monitor = DrawdownMonitor(INITIAL_CAPITAL)
    total_value = portfolio.get_total_value_estimate()
    dd_level = dd_monitor.update(total_value)
    logger.info(f"Drawdown level: {dd_level.value} ({dd_monitor.current_drawdown:.1%})")

    position_limit_override = dd_monitor.get_position_limit_override()

    # Step 6: Check existing positions for exits
    stop_calc = StopLossCalculator()
    factor_df = _load_factor_df(engine, trade_date)
    exits = []
    for code, pos in list(portfolio.positions.items()):
        price = prices.get(code, pos.current_price)
        should_exit, reason = stop_calc.check_exit(
            pos.strategy, pos.open_price, pos.open_date,
            price, pos.max_price, trade_date, pos.stop_loss_price
        )
        if should_exit:
            exits.append((code, reason, price))

    # Circuit breaker: force all exits
    if dd_level.value == "circuit_break":
        logger.warning("CIRCUIT BREAKER: forcing full liquidation")
        for code, pos in portfolio.positions.items():
            if code not in [e[0] for e in exits]:
                exits.append((code, "circuit_break", prices.get(code, pos.current_price)))

    # Step 7: Load today's signals
    signals = _load_today_signals(engine, trade_date)

    # Fill missing entry prices with close price, recalculate stop/tp
    stop_calc = StopLossCalculator()
    for sig in signals:
        if sig.entry_price <= 0 and sig.stock_code in prices:
            sig.entry_price = prices[sig.stock_code]
        if sig.entry_price > 0 and sig.stop_loss <= 0:
            atr = factor_df.at[sig.stock_code, "atr_14d"] if (
                not factor_df.empty and sig.stock_code in factor_df.index
                and "atr_14d" in factor_df.columns
            ) else None
            atr_val = float(atr) if atr and not pd.isna(atr) else None
            sig.stop_loss, sig.take_profit = stop_calc.calc_initial(
                sig.strategy, sig.entry_price, atr_val
            )

    logger.info(f"Loaded {len(signals)} signals for {trade_date}")

    # Step 8: Constraint filter
    constraint_filter = ConstraintFilter(engine)
    passed_signals, rejected = constraint_filter.filter(signals, trade_date, portfolio)

    # Block new positions if drawdown yellow+
    if not dd_monitor.allows_new_positions():
        logger.warning(f"Drawdown {dd_level.value}: blocking {len(passed_signals)} new positions")
        passed_signals = []

    # Step 9: Position sizing
    sizer = PositionSizer(INITIAL_CAPITAL)
    orders = sizer.size(passed_signals, market_state, portfolio, factor_df,
                        position_limit_override)

    # Step 10: Execute trades
    simulator = TradeSimulator()
    benchmark_return = _get_benchmark_return(engine, trade_date)
    prev_nav = _get_prev_nav(engine, trade_date)

    with session_scope() as session:
        # Sells first
        sell_trades = simulator.execute_sells(exits, portfolio, trade_date, session)
        # Then buys
        buy_trades = simulator.execute_buys(orders, portfolio, trade_date, session)
        # Update NAV
        # Re-calculate total value after trades
        portfolio.update_prices(prices)
        simulator.update_nav(portfolio, trade_date, benchmark_return, session, prev_nav)

        # Update current_price in portfolio_positions
        for code, pos in portfolio.positions.items():
            session.execute(text("""
                UPDATE portfolio_positions
                SET current_price = :price, updated_at = NOW()
                WHERE code = :code AND status = 'open'
            """), {"price": pos.current_price, "code": code})

    # Summary
    logger.info("=" * 60)
    logger.info(f"Daily summary for {trade_date}:")
    logger.info(f"  Market state: {market_state.value}")
    logger.info(f"  Signals: {len(signals)} total, {len(passed_signals)} passed filter")
    logger.info(f"  Sells: {len(sell_trades)} ({', '.join(t['code']+':'+t['reason'] for t in sell_trades) or 'none'})")
    logger.info(f"  Buys: {len(buy_trades)} ({', '.join(t['code'] for t in buy_trades) or 'none'})")
    logger.info(f"  Portfolio: {portfolio.get_total_value_estimate():,.0f} ({len(portfolio.positions)} positions)")
    logger.info(f"  Cash: {portfolio.cash:,.0f}")


def _load_prices(engine, trade_date: date) -> dict[str, float]:
    """Load close prices for all stocks on trade_date."""
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT code, close FROM stock_daily WHERE trade_date = :td"
        ), {"td": trade_date})
        return {row[0]: float(row[1]) for row in result}


def _load_today_signals(engine, trade_date: date):
    """Load Signal objects from signal_history for today."""
    from trading_system.strategies.base import Signal
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT stock_code, strategy, direction, confidence, holding_period,
                   entry_price, stop_loss, take_profit, factors_json
            FROM signal_history
            WHERE trade_date = :td AND was_executed = false
            ORDER BY confidence DESC
        """), {"td": trade_date})
        signals = []
        for row in result:
            signals.append(Signal(
                trade_date=trade_date,
                stock_code=row[0], strategy=row[1],
                direction=float(row[2]) if row[2] else 0.5,
                confidence=float(row[3]) if row[3] else 0.5,
                holding_period=row[4] or 60,
                entry_price=float(row[5]) if row[5] else 0,
                stop_loss=float(row[6]) if row[6] else 0,
                take_profit=float(row[7]) if row[7] else 0,
                factors=row[8] or {},
            ))
        return signals


def _load_factor_df(engine, trade_date: date) -> pd.DataFrame:
    """Load factor_cache for volatility adjustment."""
    df = pd.read_sql(text(
        "SELECT stock_code, volatility_20d, atr_14d FROM factor_cache WHERE trade_date = :td"
    ), engine, params={"td": trade_date})
    if df.empty:
        return pd.DataFrame()
    return df.set_index("stock_code")


def _get_benchmark_return(engine, trade_date: date) -> float:
    """Get CSI300 daily return for benchmark comparison."""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT close FROM index_daily
            WHERE code = '000300' AND trade_date <= :td
            ORDER BY trade_date DESC LIMIT 2
        """), {"td": trade_date})
        rows = [float(r[0]) for r in result]
        if len(rows) == 2:
            return (rows[0] - rows[1]) / rows[1]
    return 0.0


def _get_prev_nav(engine, trade_date: date) -> float | None:
    """Get previous day's total portfolio value."""
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT total_value FROM portfolio_nav WHERE nav_date < :td ORDER BY nav_date DESC LIMIT 1"
        ), {"td": trade_date})
        row = result.fetchone()
        return float(row[0]) if row else None


def main():
    parser = argparse.ArgumentParser(description="Run daily trading pipeline")
    parser.add_argument("--date", type=str, help="Trade date YYYY-MM-DD (default: latest)")
    parser.add_argument("--skip-factors", action="store_true", help="Skip factor computation")
    parser.add_argument("--skip-signals", action="store_true", help="Skip signal generation")
    args = parser.parse_args()

    engine = get_engine()

    if args.date:
        trade_date = date.fromisoformat(args.date)
    else:
        # Check if today is a trading day first
        from trading_system.utils.trade_calendar import is_trading_day, get_latest_trading_day
        today = date.today()
        if not is_trading_day(today):
            logger.info(f"{today} is not a trading day (weekend/holiday). Skipping.")
            return

        with engine.connect() as conn:
            result = conn.execute(text("SELECT MAX(trade_date) FROM stock_daily"))
            trade_date = result.fetchone()[0]

    logger.info(f"Running daily pipeline for {trade_date}")
    run_daily(trade_date, skip_factors=args.skip_factors, skip_signals=args.skip_signals)


if __name__ == "__main__":
    main()
