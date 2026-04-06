"""Backtest performance metrics calculation."""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class BacktestResult:
    """Complete backtest performance summary."""
    # Period
    start_date: str = ""
    end_date: str = ""
    trading_days: int = 0
    initial_capital: float = 0.0
    # Returns
    total_return: float = 0.0
    annual_return: float = 0.0
    benchmark_return: float = 0.0
    excess_return: float = 0.0
    # Risk
    max_drawdown: float = 0.0
    max_drawdown_duration: int = 0
    volatility: float = 0.0
    # Risk-adjusted
    sharpe_ratio: float = 0.0
    calmar_ratio: float = 0.0
    sortino_ratio: float = 0.0
    # Trade stats
    total_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    avg_hold_days: float = 0.0
    # Series
    nav_series: pd.DataFrame = field(default_factory=pd.DataFrame)
    trade_log: pd.DataFrame = field(default_factory=pd.DataFrame)


def calc_metrics(daily_navs: list[dict], all_trades: list[dict],
                 initial_capital: float, risk_free: float = 0.02) -> BacktestResult:
    """Calculate full backtest metrics from daily NAV and trade records.

    Args:
        daily_navs: list of dicts with keys: date, total_value, benchmark_close
        all_trades: list of dicts with keys: date, code, direction, price, shares, pnl_pct, hold_days, ...
        initial_capital: starting capital
        risk_free: annual risk-free rate (default 2%)

    Returns:
        BacktestResult with all metrics populated
    """
    result = BacktestResult(initial_capital=initial_capital)

    if not daily_navs:
        return result

    nav_df = pd.DataFrame(daily_navs)
    result.nav_series = nav_df
    result.start_date = str(nav_df["date"].iloc[0])
    result.end_date = str(nav_df["date"].iloc[-1])
    result.trading_days = len(nav_df)

    # --- Returns ---
    values = nav_df["total_value"].astype(float).values
    result.total_return = (values[-1] - initial_capital) / initial_capital

    if result.trading_days > 1:
        result.annual_return = (1 + result.total_return) ** (252 / result.trading_days) - 1

    if "benchmark_close" in nav_df.columns:
        bench = nav_df["benchmark_close"].astype(float).values
        if bench[0] > 0:
            result.benchmark_return = (bench[-1] - bench[0]) / bench[0]

    result.excess_return = result.total_return - result.benchmark_return

    # --- Daily returns ---
    daily_returns = pd.Series(values).pct_change().dropna().values
    if len(daily_returns) == 0:
        return result

    # --- Risk ---
    result.volatility = float(np.std(daily_returns, ddof=1) * np.sqrt(252))

    # Max drawdown
    peak = np.maximum.accumulate(values)
    drawdowns = (peak - values) / peak
    result.max_drawdown = float(np.max(drawdowns))

    # Max drawdown duration (trading days from peak to recovery)
    in_drawdown = drawdowns > 0
    if in_drawdown.any():
        max_dur = 0
        cur_dur = 0
        for dd in in_drawdown:
            if dd:
                cur_dur += 1
                max_dur = max(max_dur, cur_dur)
            else:
                cur_dur = 0
        result.max_drawdown_duration = max_dur

    # --- Risk-adjusted ---
    daily_rf = risk_free / 252
    excess_daily = daily_returns - daily_rf

    if result.volatility > 0:
        result.sharpe_ratio = float((result.annual_return - risk_free) / result.volatility)

    if result.max_drawdown > 0:
        result.calmar_ratio = float(result.annual_return / result.max_drawdown)

    downside = daily_returns[daily_returns < daily_rf] - daily_rf
    if len(downside) > 0:
        downside_vol = float(np.std(downside, ddof=1) * np.sqrt(252))
        if downside_vol > 0:
            result.sortino_ratio = float((result.annual_return - risk_free) / downside_vol)

    # --- Trade stats ---
    if all_trades:
        trade_df = pd.DataFrame(all_trades)
        result.trade_log = trade_df
        result.total_trades = len(trade_df)

        # Only count closed trades (sells) with pnl
        sells = trade_df[trade_df["direction"] == "SELL"].copy()
        if not sells.empty and "pnl_pct" in sells.columns:
            pnls = sells["pnl_pct"].astype(float)
            wins = pnls[pnls > 0]
            losses = pnls[pnls <= 0]

            result.win_rate = len(wins) / len(pnls) if len(pnls) > 0 else 0
            result.avg_win_pct = float(wins.mean()) if len(wins) > 0 else 0
            result.avg_loss_pct = float(losses.mean()) if len(losses) > 0 else 0

            gross_profit = wins.sum() if len(wins) > 0 else 0
            gross_loss = abs(losses.sum()) if len(losses) > 0 else 0
            result.profit_factor = float(gross_profit / gross_loss) if gross_loss > 0 else float("inf")

            if "hold_days" in sells.columns:
                result.avg_hold_days = float(sells["hold_days"].mean())

    return result
