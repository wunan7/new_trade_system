"""Backtest engine: replay historical trading days through the full pipeline in memory."""
from datetime import date

import numpy as np
import pandas as pd
from loguru import logger
from sqlalchemy import text

from trading_system.strategies.market_state import MarketStateDetector
from trading_system.strategies.value import ValueStrategy
from trading_system.strategies.growth import GrowthStrategy
from trading_system.strategies.momentum import MomentumStrategy
from trading_system.strategies.event_driven import EventDrivenStrategy
from trading_system.strategies.base import Signal, STRATEGY_WEIGHTS, MarketState
from trading_system.risk.constraints import ConstraintFilter
from trading_system.risk.position_sizer import PositionSizer
from trading_system.risk.stop_loss import StopLossCalculator
from trading_system.risk.drawdown_monitor import DrawdownMonitor
from trading_system.execution.portfolio import Portfolio, PositionRecord
from trading_system.execution.cost_model import calc_trade_cost
from trading_system.backtest.metrics import BacktestResult, calc_metrics


class BacktestEngine:
    """Event-driven backtest engine that replays trading days in memory."""

    def __init__(self, initial_capital: float = 1_000_000, engine=None):
        if engine is None:
            from trading_system.db.engine import get_engine
            engine = get_engine()
        self.engine = engine
        self.capital = initial_capital

        # Components (reuse existing Layer 3-4)
        self.detector = MarketStateDetector(engine)
        self.strategies = {
            "value": ValueStrategy(),
            "growth": GrowthStrategy(),
            "momentum": MomentumStrategy(),
            "event": EventDrivenStrategy(engine),
        }
        self.constraint_filter = ConstraintFilter(engine)
        self.sizer = PositionSizer(initial_capital)
        self.stop_calc = StopLossCalculator()

        # State
        self.portfolio = Portfolio(initial_capital)
        self.dd_monitor = DrawdownMonitor(initial_capital)

        # Result collection (in memory, no DB writes)
        self.daily_navs: list[dict] = []
        self.all_trades: list[dict] = []

    def run(self, start_date: date, end_date: date) -> BacktestResult:
        """Run backtest over a date range. Returns BacktestResult."""
        trading_days = self._get_trading_days(start_date, end_date)
        if not trading_days:
            logger.warning("No trading days found in range")
            return BacktestResult()

        # Pre-load benchmark data
        benchmark = self._load_benchmark(start_date, end_date)

        logger.info(f"Backtest: {start_date} ~ {end_date}, {len(trading_days)} days, capital={self.capital:,.0f}")

        for i, td in enumerate(trading_days):
            bench_close = benchmark.get(td, 0)
            self._step(td, bench_close)

            if (i + 1) % 20 == 0 or i == len(trading_days) - 1:
                nav = self.portfolio.get_total_value_estimate()
                ret = (nav - self.capital) / self.capital
                logger.info(f"  [{i+1}/{len(trading_days)}] {td} NAV={nav:,.0f} ({ret:+.2%})")

        return calc_metrics(self.daily_navs, self.all_trades, self.capital)

    def _step(self, trade_date: date, benchmark_close: float):
        """Process one trading day."""
        # 1. Load prices
        prices = self._load_prices(trade_date)
        if not prices:
            return
        self.portfolio.update_prices(prices)

        # 2. Market state
        try:
            market_state = self.detector.detect(trade_date)
        except Exception:
            market_state = MarketState.NEUTRAL_LOW

        # 3. Drawdown check
        total_value = self.portfolio.get_total_value_estimate()
        dd_level = self.dd_monitor.update(total_value)
        position_limit = self.dd_monitor.get_position_limit_override()

        # 4. Check exits on existing positions
        exits = []
        for code, pos in list(self.portfolio.positions.items()):
            price = prices.get(code, pos.current_price)
            should_exit, reason = self.stop_calc.check_exit(
                pos.strategy, pos.open_price, pos.open_date,
                price, pos.max_price, trade_date, pos.stop_loss_price
            )
            if should_exit:
                exits.append((code, reason, price))

        # Circuit breaker
        if dd_level.value == "circuit_break":
            for code, pos in self.portfolio.positions.items():
                if code not in [e[0] for e in exits]:
                    exits.append((code, "circuit_break", prices.get(code, pos.current_price)))

        # 5. Execute sells (in memory)
        for code, reason, sell_price in exits:
            self._execute_sell(code, reason, sell_price, trade_date)

        # 6. Generate signals (directly from factor_cache, no DB write)
        signals = []
        if self.dd_monitor.allows_new_positions():
            signals = self._generate_signals(trade_date, market_state)

        # 7. Constraint filter
        passed, rejected = self.constraint_filter.filter(signals, trade_date, self.portfolio)

        # 8. Position sizing
        factor_df = self._load_factor_df(trade_date)
        orders = self.sizer.size(passed, market_state, self.portfolio, factor_df, position_limit)

        # 9. Execute buys (in memory)
        for order in orders:
            self._execute_buy(order, trade_date, factor_df, prices)

        # 10. Record daily NAV
        total_value = self.portfolio.get_total_value_estimate()
        self.daily_navs.append({
            "date": trade_date,
            "total_value": total_value,
            "cash": self.portfolio.cash,
            "positions_count": len(self.portfolio.positions),
            "benchmark_close": benchmark_close,
            "market_state": market_state.value,
            "drawdown_level": dd_level.value,
        })

    def _generate_signals(self, trade_date: date, market_state: MarketState) -> list[Signal]:
        """Generate signals directly from factor_cache without writing to DB."""
        factor_df = self._load_factor_df(trade_date)
        if factor_df.empty:
            return []

        weights = STRATEGY_WEIGHTS[market_state]
        all_signals = []

        for name, strategy in self.strategies.items():
            if weights.get(name, 0) == 0:
                continue
            sigs = strategy.generate(trade_date, factor_df)
            all_signals.extend(sigs)

        if not all_signals:
            return []

        # Aggregate same-stock signals (reuse logic from SignalGenerator)
        from collections import defaultdict
        by_stock = defaultdict(list)
        for sig in all_signals:
            by_stock[sig.stock_code].append(sig)

        aggregated = []
        for stock_code, sigs in by_stock.items():
            if len(sigs) == 1:
                aggregated.append(sigs[0])
            else:
                total_w = sum(weights.get(s.strategy, 0) for s in sigs)
                if total_w == 0:
                    continue
                merged = Signal(
                    trade_date=trade_date, stock_code=stock_code, strategy="multi",
                    direction=sum(s.direction * weights.get(s.strategy, 0) for s in sigs) / total_w,
                    confidence=sum(s.confidence * weights.get(s.strategy, 0) for s in sigs) / total_w,
                    holding_period=max(s.holding_period for s in sigs),
                    entry_price=0, stop_loss=0, take_profit=0,
                    factors={k: v for s in sigs for k, v in s.factors.items()},
                )
                aggregated.append(merged)

        # Fill entry prices
        prices = self._load_prices(trade_date)

        # IC/IR confidence adjustment
        from trading_system.signals.generator import IC_WEIGHTS
        zscore_data = {}
        if "factors_json" in factor_df.columns:
            for code in factor_df.index:
                fj = factor_df.at[code, "factors_json"]
                if isinstance(fj, dict) and "zscore" in fj:
                    zscore_data[code] = fj["zscore"]
        if zscore_data:
            zscore_df = pd.DataFrame.from_dict(zscore_data, orient="index")
            for sig in aggregated:
                if sig.stock_code not in zscore_df.index:
                    continue
                row = zscore_df.loc[sig.stock_code]
                ws, tw = 0.0, 0.0
                for fn, iw in IC_WEIGHTS.items():
                    if fn in row.index and pd.notna(row[fn]):
                        ws += float(row[fn]) * iw
                        tw += abs(iw)
                if tw > 0:
                    sig.confidence = float(np.clip(sig.confidence + (ws / tw) * 0.1, 0.3, 0.95))

        for sig in aggregated:
            if (sig.entry_price is None or sig.entry_price <= 0) and sig.stock_code in prices:
                sig.entry_price = prices[sig.stock_code]
            if sig.entry_price and sig.entry_price > 0 and (sig.stop_loss is None or sig.stop_loss <= 0):
                atr = self._get_atr(sig.stock_code, trade_date)
                sig.stop_loss, sig.take_profit = self.stop_calc.calc_initial(
                    sig.strategy, sig.entry_price, atr
                )

        return aggregated

    def _execute_buy(self, order, trade_date: date, factor_df, prices):
        """Execute buy in memory only."""
        sig = order.signal
        code = sig.stock_code

        if code in self.portfolio.positions:
            return

        amount = sig.entry_price * order.shares
        cost_info = calc_trade_cost(sig.entry_price, order.shares, "BUY")
        total_cost = amount + cost_info["total"]

        if total_cost > self.portfolio.cash:
            return

        pos = PositionRecord(
            code=code, open_date=trade_date, open_price=sig.entry_price,
            shares=order.shares, strategy=sig.strategy, signal_id=None,
            stop_loss_price=sig.stop_loss, take_profit_price=sig.take_profit,
            max_hold_days=sig.holding_period, max_price=sig.entry_price,
            current_price=sig.entry_price,
        )
        self.portfolio.add_position(pos, cost_info["total"])

        self.all_trades.append({
            "date": trade_date, "code": code, "direction": "BUY",
            "price": sig.entry_price, "shares": order.shares,
            "amount": amount, "cost": cost_info["total"],
            "strategy": sig.strategy,
        })

    def _execute_sell(self, code: str, reason: str, sell_price: float, trade_date: date):
        """Execute sell in memory only."""
        pos = self.portfolio.positions.get(code)
        if pos is None:
            return

        cost_info = calc_trade_cost(sell_price, pos.shares, "SELL")
        pnl_pct = (sell_price - pos.open_price) / pos.open_price
        hold_days = (trade_date - pos.open_date).days

        self.all_trades.append({
            "date": trade_date, "code": code, "direction": "SELL",
            "price": sell_price, "shares": pos.shares,
            "amount": sell_price * pos.shares, "cost": cost_info["total"],
            "strategy": pos.strategy, "reason": reason,
            "pnl_pct": round(pnl_pct, 4), "hold_days": hold_days,
        })

        self.portfolio.close_position(code, sell_price, cost_info["total"])

    # --- Data loading helpers ---

    def _get_trading_days(self, start_date: date, end_date: date) -> list[date]:
        with self.engine.connect() as conn:
            result = conn.execute(text(
                "SELECT DISTINCT trade_date FROM factor_cache "
                "WHERE trade_date BETWEEN :s AND :e ORDER BY trade_date"
            ), {"s": start_date, "e": end_date})
            return [row[0] for row in result]

    _price_cache: dict = {}

    def _load_prices(self, trade_date: date) -> dict[str, float]:
        if trade_date in self._price_cache:
            return self._price_cache[trade_date]
        with self.engine.connect() as conn:
            result = conn.execute(text(
                "SELECT code, close FROM stock_daily WHERE trade_date = :td"
            ), {"td": trade_date})
            prices = {row[0]: float(row[1]) for row in result}
        self._price_cache[trade_date] = prices
        return prices

    _factor_cache: dict = {}

    def _load_factor_df(self, trade_date: date) -> pd.DataFrame:
        if trade_date in self._factor_cache:
            return self._factor_cache[trade_date]
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
                   sentiment_score, news_heat, news_mention_count,
                   factors_json
            FROM factor_cache WHERE trade_date = :td
        """
        df = pd.read_sql(text(sql), self.engine, params={"td": trade_date})
        if df.empty:
            self._factor_cache[trade_date] = pd.DataFrame()
            return pd.DataFrame()
        df = df.set_index("stock_code")
        self._factor_cache[trade_date] = df
        return df

    def _load_benchmark(self, start_date: date, end_date: date) -> dict[date, float]:
        with self.engine.connect() as conn:
            result = conn.execute(text(
                "SELECT trade_date, close FROM index_daily "
                "WHERE code = '000300' AND trade_date BETWEEN :s AND :e ORDER BY trade_date"
            ), {"s": start_date, "e": end_date})
            return {row[0]: float(row[1]) for row in result}

    def _get_atr(self, code: str, trade_date: date) -> float | None:
        df = self._load_factor_df(trade_date)
        if df.empty or code not in df.index or "atr_14d" not in df.columns:
            return None
        val = df.at[code, "atr_14d"]
        if val is None or pd.isna(val):
            return None
        return float(val)
