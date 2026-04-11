"""Factor IC/IR analysis for evaluating factor effectiveness.

Computes Rank IC (Spearman correlation between factor values and forward returns)
for each factor across time, producing IC mean, IC std, IR, IC win rate, and t-stat.
"""
from datetime import date, timedelta
import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy import text
from loguru import logger


def calc_rank_ic(factor_values: pd.Series, forward_returns: pd.Series) -> float:
    """Compute Rank IC (Spearman correlation) between factor and forward returns.

    Both inputs should be indexed by stock_code with matching indices.
    Returns NaN if insufficient data.
    """
    aligned = pd.concat([factor_values, forward_returns], axis=1, keys=["factor", "ret"]).dropna()
    if len(aligned) < 30:
        return np.nan
    corr, _ = stats.spearmanr(aligned["factor"], aligned["ret"])
    return corr


def _get_monthly_dates(engine, start_date: date, end_date: date) -> list[date]:
    """Get the last trading day of each month in the range."""
    sql = text("""
        SELECT DISTINCT trade_date FROM factor_cache
        WHERE trade_date BETWEEN :start AND :end
        ORDER BY trade_date
    """)
    with engine.connect() as conn:
        all_dates = [r[0] for r in conn.execute(sql, {"start": start_date, "end": end_date})]

    monthly = {}
    for d in all_dates:
        key = (d.year, d.month)
        monthly[key] = d  # last date wins
    return sorted(monthly.values())


def _load_factor_data(engine, trade_date: date, factor_names: list[str]) -> pd.DataFrame:
    """Load factor values for a given date from factor_cache."""
    cols = ", ".join(factor_names)
    sql = text(f"""
        SELECT stock_code, {cols}
        FROM factor_cache
        WHERE trade_date = :date
    """)
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"date": trade_date})
    if df.empty:
        return pd.DataFrame()
    df = df.set_index("stock_code")
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _load_forward_returns(engine, trade_date: date, forward_days: int = 20) -> pd.Series:
    """Load forward returns (N-day) for stocks from trade_date.

    Returns Series indexed by stock_code.
    """
    sql = text("""
        WITH base AS (
            SELECT code, close FROM stock_daily WHERE trade_date = :base_date
        ),
        forward AS (
            SELECT DISTINCT ON (code) code, close
            FROM stock_daily
            WHERE trade_date > :base_date AND trade_date <= :end_date
            ORDER BY code, trade_date DESC
        )
        SELECT b.code, (f.close - b.close) / NULLIF(b.close, 0) AS fwd_return
        FROM base b JOIN forward f ON b.code = f.code
    """)
    end_date = trade_date + timedelta(days=int(forward_days * 1.6))
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"base_date": trade_date, "end_date": end_date})
    if df.empty:
        return pd.Series(dtype=float)
    df["fwd_return"] = pd.to_numeric(df["fwd_return"], errors="coerce")
    return df.set_index("code")["fwd_return"]


def evaluate_all_factors(engine, start_date: date, end_date: date,
                         factor_names: list[str] = None,
                         forward_days: int = 20) -> pd.DataFrame:
    """Evaluate IC/IR for all factors over the given period.

    Args:
        engine: SQLAlchemy engine
        start_date: evaluation start date
        end_date: evaluation end date
        factor_names: list of factor column names (default: all from factor_cache)
        forward_days: forward return period in trading days

    Returns:
        DataFrame with columns: factor, ic_mean, ic_std, ir, ic_win_rate, t_stat, n_months
        Sorted by |IR| descending.
    """
    if factor_names is None:
        from trading_system.pipeline.orchestrator import FactorPipeline
        factor_names = FactorPipeline.ALL_FACTORS

    monthly_dates = _get_monthly_dates(engine, start_date, end_date)
    # Drop last month (no forward returns available)
    if len(monthly_dates) > 1:
        monthly_dates = monthly_dates[:-1]

    logger.info(f"Evaluating {len(factor_names)} factors across {len(monthly_dates)} months "
                f"({monthly_dates[0]} ~ {monthly_dates[-1]})")

    ic_records = {f: [] for f in factor_names}

    for eval_date in monthly_dates:
        factor_df = _load_factor_data(engine, eval_date, factor_names)
        fwd_returns = _load_forward_returns(engine, eval_date, forward_days)

        if factor_df.empty or fwd_returns.empty:
            continue

        for factor_name in factor_names:
            if factor_name not in factor_df.columns:
                continue
            ic = calc_rank_ic(factor_df[factor_name], fwd_returns)
            if not np.isnan(ic):
                ic_records[factor_name].append(ic)

    results = []
    for factor_name in factor_names:
        ics = ic_records[factor_name]
        n = len(ics)
        if n < 3:
            results.append({
                "factor": factor_name,
                "ic_mean": np.nan, "ic_std": np.nan, "ir": np.nan,
                "ic_win_rate": np.nan, "t_stat": np.nan, "n_months": n
            })
            continue

        ic_arr = np.array(ics)
        ic_mean = ic_arr.mean()
        ic_std = ic_arr.std(ddof=1)
        ir = ic_mean / ic_std if ic_std > 0 else 0.0
        ic_win_rate = (ic_arr > 0).mean()
        t_stat = ic_mean / (ic_std / np.sqrt(n)) if ic_std > 0 else 0.0

        results.append({
            "factor": factor_name,
            "ic_mean": round(ic_mean, 4),
            "ic_std": round(ic_std, 4),
            "ir": round(ir, 4),
            "ic_win_rate": round(ic_win_rate, 4),
            "t_stat": round(t_stat, 2),
            "n_months": n,
        })

    df = pd.DataFrame(results)
    df["abs_ir"] = df["ir"].abs()
    df = df.sort_values("abs_ir", ascending=False).drop(columns=["abs_ir"])
    return df.reset_index(drop=True)
