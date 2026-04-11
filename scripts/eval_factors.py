"""Evaluate factor IC/IR across the backtest period."""
import sys
import codecs
from datetime import date
import pandas as pd

sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())

from trading_system.factors.ic_analysis import evaluate_all_factors
from trading_system.db.engine import get_engine
from loguru import logger

logger.remove()
logger.add(sys.stderr, level="INFO")

engine = get_engine()

print("=" * 80)
print("  因子 IC/IR 评估报告")
print(f"  评估区间: 2023-04-03 ~ 2026-03-03 (前瞻20日收益)")
print("=" * 80)

result = evaluate_all_factors(
    engine,
    start_date=date(2023, 4, 3),
    end_date=date(2026, 3, 3),
    forward_days=20,
)

print()
print(f"{'Factor':<25} {'IC_Mean':>8} {'IC_Std':>8} {'IR':>8} {'IC_Win%':>8} {'t_stat':>7} {'Months':>7}")
print("-" * 80)

for _, row in result.iterrows():
    ic_mean = f"{row['ic_mean']:.4f}" if not pd.isna(row['ic_mean']) else "   N/A"
    ic_std = f"{row['ic_std']:.4f}" if not pd.isna(row['ic_std']) else "   N/A"
    ir = f"{row['ir']:.4f}" if not pd.isna(row['ir']) else "   N/A"
    win = f"{row['ic_win_rate']:.1%}" if not pd.isna(row['ic_win_rate']) else "   N/A"
    t = f"{row['t_stat']:.2f}" if not pd.isna(row['t_stat']) else "   N/A"

    # Mark effectiveness level
    abs_ir = abs(row['ir']) if not pd.isna(row['ir']) else 0
    if abs_ir >= 0.5:
        marker = " ★★★"
    elif abs_ir >= 0.3:
        marker = " ★★"
    elif abs_ir >= 0.1:
        marker = " ★"
    else:
        marker = ""

    print(f"{row['factor']:<25} {ic_mean:>8} {ic_std:>8} {ir:>8} {win:>8} {t:>7} {row['n_months']:>7}{marker}")

print("-" * 80)
print("  ★★★ IR≥0.5 有效  ★★ IR≥0.3 边际有效  ★ IR≥0.1 弱有效")
print("=" * 80)
