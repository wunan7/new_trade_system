"""Generate monthly paper trading attribution report from trade_log and portfolio_nav."""
import argparse
import calendar
import codecs
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from trading_system.db.engine import get_engine

sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())


ROOT_DIR = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT_DIR / "docs" / "monthly-reports"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate monthly paper trading report")
    parser.add_argument("--month", required=True, help="Month in YYYY-MM format")
    return parser.parse_args()


def get_month_range(month: str) -> tuple[str, str]:
    try:
        year = int(month[:4])
        mon = int(month[5:7])
        if len(month) != 7 or month[4] != "-":
            raise ValueError
    except (ValueError, IndexError):
        raise ValueError("--month must be in YYYY-MM format") from None

    last_day = calendar.monthrange(year, mon)[1]
    return f"{year:04d}-{mon:02d}-01", f"{year:04d}-{mon:02d}-{last_day:02d}"


def load_trade_log(engine, start_date: str, end_date: str) -> pd.DataFrame:
    sql = text(
        """
        SELECT trade_date, code, direction, price, shares, amount, strategy,
               commission, stamp_tax, slippage, position_id
        FROM trade_log
        WHERE is_paper = true
          AND trade_date >= :start_date
          AND trade_date <= :end_date
        ORDER BY trade_date, id
        """
    )
    df = pd.read_sql(sql, engine, params={"start_date": start_date, "end_date": end_date})
    if df.empty:
        return df

    df["trade_date"] = pd.to_datetime(df["trade_date"])
    numeric_cols = ["price", "shares", "amount", "commission", "stamp_tax", "slippage"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    df["strategy"] = df["strategy"].fillna("unknown")
    df["total_cost"] = df["commission"] + df["stamp_tax"] + df["slippage"]
    return df


def load_portfolio_nav(engine, start_date: str, end_date: str) -> pd.DataFrame:
    sql = text(
        """
        SELECT nav_date, total_value, cash, positions_value, position_count,
               daily_return, cumulative_return, benchmark_return, excess_return,
               drawdown, max_drawdown, sharpe_30d
        FROM portfolio_nav
        WHERE is_paper = true
          AND nav_date >= :start_date
          AND nav_date <= :end_date
        ORDER BY nav_date
        """
    )
    df = pd.read_sql(sql, engine, params={"start_date": start_date, "end_date": end_date})
    if df.empty:
        return df

    df["nav_date"] = pd.to_datetime(df["nav_date"])
    numeric_cols = [
        "total_value", "cash", "positions_value", "position_count", "daily_return",
        "cumulative_return", "benchmark_return", "excess_return", "drawdown",
        "max_drawdown", "sharpe_30d",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def fmt_currency(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value):,.2f}"


def fmt_pct(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value):+.2%}"


def fmt_ratio(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value):.2%}"


def compute_summary(trades: pd.DataFrame, nav: pd.DataFrame) -> dict:
    start_nav = float(nav.iloc[0]["total_value"])
    end_nav = float(nav.iloc[-1]["total_value"])
    monthly_return = (end_nav / start_nav - 1.0) if start_nav else None

    total_commission = float(trades["commission"].sum()) if not trades.empty else 0.0
    total_stamp_tax = float(trades["stamp_tax"].sum()) if not trades.empty else 0.0
    total_slippage = float(trades["slippage"].sum()) if not trades.empty else 0.0
    total_cost = float(trades["total_cost"].sum()) if not trades.empty else 0.0
    total_trade_count = int(len(trades))
    small_trade_count = int((trades["amount"] < 10_000).sum()) if not trades.empty else 0

    net_profit = end_nav - start_nav
    gross_profit = net_profit + total_cost
    cost_to_gross_profit_ratio = (total_cost / gross_profit) if gross_profit > 0 else None

    return {
        "start_nav": start_nav,
        "end_nav": end_nav,
        "monthly_return": monthly_return,
        "total_trade_count": total_trade_count,
        "total_commission": total_commission,
        "total_stamp_tax": total_stamp_tax,
        "total_slippage": total_slippage,
        "total_cost": total_cost,
        "small_trade_count": small_trade_count,
        "net_profit": net_profit,
        "gross_profit": gross_profit,
        "cost_to_gross_profit_ratio": cost_to_gross_profit_ratio,
        "trading_days": int(len(nav)),
    }


def build_strategy_stats(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()

    grouped = trades.groupby("strategy", dropna=False)
    stats = grouped.agg(
        trade_count=("code", "size"),
        buy_count=("direction", lambda s: int((s == "BUY").sum())),
        sell_count=("direction", lambda s: int((s == "SELL").sum())),
        total_amount=("amount", "sum"),
        total_commission=("commission", "sum"),
        total_stamp_tax=("stamp_tax", "sum"),
        total_slippage=("slippage", "sum"),
        total_cost=("total_cost", "sum"),
        small_trade_count=("amount", lambda s: int((s < 10_000).sum())),
    ).reset_index()
    stats = stats.sort_values(["trade_count", "total_amount"], ascending=[False, False])
    return stats


def build_stock_stats(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()

    grouped = trades.groupby("code", dropna=False)
    stats = grouped.agg(
        trade_count=("code", "size"),
        buy_count=("direction", lambda s: int((s == "BUY").sum())),
        sell_count=("direction", lambda s: int((s == "SELL").sum())),
        total_amount=("amount", "sum"),
        total_cost=("total_cost", "sum"),
    ).reset_index()

    strategy_mix_source = (
        trades.groupby(["code", "strategy"]).size().reset_index(name="cnt")
        .sort_values(["code", "cnt", "strategy"], ascending=[True, False, True])
    )
    strategy_mix = (
        strategy_mix_source.groupby("code").agg(
            strategy_mix=("strategy", lambda s: ", ".join(
                f"{strategy}({int(cnt)})"
                for strategy, cnt in zip(s, strategy_mix_source.loc[s.index, "cnt"])
            ))
        ).reset_index()
    )

    stats = stats.merge(strategy_mix, on="code", how="left")
    stats = stats.sort_values(["trade_count", "total_amount", "code"], ascending=[False, False, True]).head(20)
    return stats


def render_markdown(month: str, start_date: str, end_date: str, summary: dict,
                    strategy_stats: pd.DataFrame, stock_stats: pd.DataFrame) -> str:
    lines: list[str] = []
    lines.append(f"# {month} 模拟盘归因报告")
    lines.append("")
    lines.append(f"**统计区间**：{start_date} ~ {end_date}")
    lines.append(f"**报告范围**：trade_log + portfolio_nav（模拟盘）")
    lines.append("")

    lines.append("## 1. 月度概览")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("|------|------:|")
    lines.append(f"| 起始净值 | {fmt_currency(summary['start_nav'])} |")
    lines.append(f"| 期末净值 | {fmt_currency(summary['end_nav'])} |")
    lines.append(f"| 月度收益率 | {fmt_pct(summary['monthly_return'])} |")
    lines.append(f"| 月内净收益 | {fmt_currency(summary['net_profit'])} |")
    lines.append(f"| 月内毛收益（净收益+成本） | {fmt_currency(summary['gross_profit'])} |")
    lines.append(f"| 交易日数 | {summary['trading_days']} |")
    lines.append(f"| 总交易笔数 | {summary['total_trade_count']} |")
    lines.append(f"| 小单笔数（amount < 10000） | {summary['small_trade_count']} |")
    lines.append(f"| 总佣金 | {fmt_currency(summary['total_commission'])} |")
    lines.append(f"| 总印花税 | {fmt_currency(summary['total_stamp_tax'])} |")
    lines.append(f"| 总滑点 | {fmt_currency(summary['total_slippage'])} |")
    lines.append(f"| 总交易成本 | {fmt_currency(summary['total_cost'])} |")
    ratio_text = fmt_ratio(summary['cost_to_gross_profit_ratio']) if summary['cost_to_gross_profit_ratio'] is not None else "N/A（本月毛收益<=0）"
    lines.append(f"| 成本 / 毛收益比 | {ratio_text} |")
    lines.append("")

    lines.append("## 2. 按策略统计")
    lines.append("")
    if strategy_stats.empty:
        lines.append("本月无交易记录。")
    else:
        lines.append("| 策略 | 交易笔数 | 买入 | 卖出 | 成交额 | 佣金 | 印花税 | 滑点 | 总成本 | 小单笔数 |")
        lines.append("|------|--------:|----:|----:|------:|------:|--------:|------:|--------:|----------:|")
        for _, row in strategy_stats.iterrows():
            lines.append(
                f"| {row['strategy']} | {int(row['trade_count'])} | {int(row['buy_count'])} | {int(row['sell_count'])} | "
                f"{fmt_currency(row['total_amount'])} | {fmt_currency(row['total_commission'])} | {fmt_currency(row['total_stamp_tax'])} | "
                f"{fmt_currency(row['total_slippage'])} | {fmt_currency(row['total_cost'])} | {int(row['small_trade_count'])} |"
            )
    lines.append("")

    lines.append("## 3. 按股票统计（Top 20 by trade count）")
    lines.append("")
    if stock_stats.empty:
        lines.append("本月无交易记录。")
    else:
        lines.append("| 股票代码 | 交易笔数 | 买入 | 卖出 | 成交额 | 总成本 | 策略分布 |")
        lines.append("|----------|--------:|----:|----:|------:|--------:|----------|")
        for _, row in stock_stats.iterrows():
            lines.append(
                f"| {row['code']} | {int(row['trade_count'])} | {int(row['buy_count'])} | {int(row['sell_count'])} | "
                f"{fmt_currency(row['total_amount'])} | {fmt_currency(row['total_cost'])} | {row['strategy_mix']} |"
            )
    lines.append("")

    lines.append("## 4. 说明")
    lines.append("")
    lines.append("- 本报告为 standalone 脚本生成，数据来源仅限 `trade_log` 与 `portfolio_nav` 的模拟盘记录（`is_paper = true`）。")
    lines.append("- 月度收益率按月内首个净值与月内末个净值计算：`end_nav / start_nav - 1`。")
    lines.append("- 总交易成本 = 佣金 + 印花税 + 滑点。")
    lines.append("- 成本 / 毛收益比中的毛收益按 `（期末净值 - 起始净值） + 总交易成本` 估算；若毛收益小于等于 0，则显示为 N/A。")
    lines.append("- 小单定义为单笔成交金额 `amount < 10000`。")
    lines.append("- 按股票统计仅展示当月交易笔数最多的前 20 只股票。")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    start_date, end_date = get_month_range(args.month)
    engine = get_engine()

    trades = load_trade_log(engine, start_date, end_date)
    nav = load_portfolio_nav(engine, start_date, end_date)

    if nav.empty:
        raise SystemExit(f"No portfolio_nav data found for {args.month}")

    summary = compute_summary(trades, nav)
    strategy_stats = build_strategy_stats(trades)
    stock_stats = build_stock_stats(trades)
    markdown = render_markdown(args.month, start_date, end_date, summary, strategy_stats, stock_stats)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = REPORT_DIR / f"{args.month}-paper-trading-report.md"
    output_path.write_text(markdown, encoding="utf-8")

    print(f"Report written to: {output_path}")
    print(f"Trades: {summary['total_trade_count']}, Start NAV: {summary['start_nav']:,.2f}, End NAV: {summary['end_nav']:,.2f}, Return: {summary['monthly_return']:+.2%}")


if __name__ == "__main__":
    main()
