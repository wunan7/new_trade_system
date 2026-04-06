"""Run backtest and print results."""
import sys
import codecs
from datetime import date

sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())

from trading_system.backtest.engine import BacktestEngine
from loguru import logger

# Suppress verbose logs during backtest
logger.remove()
logger.add(sys.stderr, level="WARNING")

print("Starting backtest...")
engine = BacktestEngine(initial_capital=1_000_000)
result = engine.run(start_date=date(2023, 4, 3), end_date=date(2026, 4, 3))

print()
print("=" * 60)
print("  MVP 回测报告")
print(f"  回测区间: {result.start_date} ~ {result.end_date}")
print(f"  交易天数: {result.trading_days}")
print(f"  初始资金: {result.initial_capital:,.0f}")
print("=" * 60)
print()
print("  ── 收益 ──")
print(f"  总收益率:      {result.total_return:+.2%}")
print(f"  年化收益率:    {result.annual_return:+.2%}")
print(f"  基准收益率:    {result.benchmark_return:+.2%} (沪深300)")
print(f"  超额收益:      {result.excess_return:+.2%}")
print()
print("  ── 风险 ──")
print(f"  最大回撤:      {result.max_drawdown:.2%}")
print(f"  最大回撤持续:  {result.max_drawdown_duration} 天")
print(f"  年化波动率:    {result.volatility:.2%}")
print()
print("  ── 风险调整收益 ──")
print(f"  夏普比率:      {result.sharpe_ratio:.2f}")
print(f"  卡尔玛比率:    {result.calmar_ratio:.2f}")
print(f"  索提诺比率:    {result.sortino_ratio:.2f}")
print()
print("  ── 交易统计 ──")
print(f"  总交易次数:    {result.total_trades}")

# Count sells (closed trades)
if not result.trade_log.empty:
    sells = result.trade_log[result.trade_log["direction"] == "SELL"]
    buys = result.trade_log[result.trade_log["direction"] == "BUY"]
    print(f"    买入次数:    {len(buys)}")
    print(f"    卖出次数:    {len(sells)}")

print(f"  胜率:          {result.win_rate:.2%}")
print(f"  平均盈利:      {result.avg_win_pct:+.2%}")
print(f"  平均亏损:      {result.avg_loss_pct:+.2%}")
print(f"  盈亏比:        {result.profit_factor:.2f}")
print(f"  平均持仓天数:  {result.avg_hold_days:.1f}")
print("=" * 60)

# NAV series summary
nav = result.nav_series
if not nav.empty:
    print()
    print(f"  起始净值: {nav['total_value'].iloc[0]:,.0f}")
    print(f"  结束净值: {nav['total_value'].iloc[-1]:,.0f}")

    # Market state distribution
    if 'market_state' in nav.columns:
        print()
        print("  市场状态分布:")
        for state, count in nav['market_state'].value_counts().items():
            print(f"    {state}: {count} 天 ({count/len(nav)*100:.1f}%)")

    # Monthly returns
    nav['date'] = nav['date'].astype(str)
    nav['month'] = nav['date'].str[:7]
    nav['daily_ret'] = nav['total_value'].pct_change()
    monthly = nav.groupby('month')['daily_ret'].apply(lambda x: (1+x).prod()-1)
    print()
    print("  月度收益:")
    for month, ret in monthly.items():
        print(f"    {month}: {ret:+.2%}")

    # Strategy distribution in trades
    if not result.trade_log.empty and 'strategy' in result.trade_log.columns:
        print()
        print("  策略信号分布 (买入):")
        buy_trades = result.trade_log[result.trade_log["direction"] == "BUY"]
        for strat, count in buy_trades['strategy'].value_counts().items():
            print(f"    {strat}: {count} 次")

print()
print("=" * 60)
