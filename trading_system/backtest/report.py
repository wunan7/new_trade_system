"""Backtest report generation: terminal output + CSV export."""
import os
from trading_system.backtest.metrics import BacktestResult


def print_report(result: BacktestResult):
    """Print backtest summary to terminal."""
    print()
    print("=" * 56)
    print("              BACKTEST REPORT")
    print("=" * 56)
    print(f"  Period:  {result.start_date} ~ {result.end_date} ({result.trading_days} days)")
    print(f"  Capital: {result.initial_capital:,.0f}")
    print()
    print("--- Returns ---")
    print(f"  Total Return:     {result.total_return:+.2%}")
    print(f"  Annual Return:    {result.annual_return:+.2%}")
    print(f"  Benchmark Return: {result.benchmark_return:+.2%}")
    print(f"  Excess Return:    {result.excess_return:+.2%}")
    print()
    print("--- Risk ---")
    print(f"  Max Drawdown:     {result.max_drawdown:.2%} ({result.max_drawdown_duration} days)")
    print(f"  Volatility:       {result.volatility:.2%}")
    print()
    print("--- Risk-Adjusted ---")
    print(f"  Sharpe Ratio:     {result.sharpe_ratio:.2f}")
    print(f"  Sortino Ratio:    {result.sortino_ratio:.2f}")
    print(f"  Calmar Ratio:     {result.calmar_ratio:.2f}")
    print()
    print("--- Trade Stats ---")
    print(f"  Total Trades:     {result.total_trades}")
    print(f"  Win Rate:         {result.win_rate:.1%}")
    print(f"  Profit Factor:    {result.profit_factor:.2f}")
    print(f"  Avg Win:          {result.avg_win_pct:+.2%}")
    print(f"  Avg Loss:         {result.avg_loss_pct:+.2%}")
    print(f"  Avg Hold Days:    {result.avg_hold_days:.1f}")
    print("=" * 56)


def export_csv(result: BacktestResult, output_dir: str = "backtest_results"):
    """Export NAV series and trade log to CSV files."""
    os.makedirs(output_dir, exist_ok=True)

    if not result.nav_series.empty:
        nav_path = os.path.join(output_dir, "nav_series.csv")
        result.nav_series.to_csv(nav_path, index=False)
        print(f"  NAV series exported to {nav_path}")

    if not result.trade_log.empty:
        trade_path = os.path.join(output_dir, "trade_log.csv")
        result.trade_log.to_csv(trade_path, index=False)
        print(f"  Trade log exported to {trade_path}")
