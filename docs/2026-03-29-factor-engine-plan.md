# Factor Calculation Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a factor calculation engine that reads existing A-share market data from the `finance` PostgreSQL database, computes ~25 quantitative factors (technical + fundamental), standardizes them cross-sectionally, and writes results to a `factor_cache` table.

**Architecture:** New Python package `trading_system` at `C:\Users\wunan\projects\new_solution\`. It imports `finance_data` (existing package, `pip install -e`) for DB connection and query helpers. Factor computation is modular: pure functions per factor, an orchestrator pipeline loads data → computes → standardizes → writes. Raw SQL + pandas for bulk data loading; SQLAlchemy model for the output table.

**Tech Stack:** Python 3.11+, SQLAlchemy 2.0, pandas, numpy, scipy, loguru, pydantic-settings, pytest. Reuses `finance_data.indicators.technical` (calc_macd, calc_adx, calc_atr, calc_bollinger) and `finance_data.utils.bulk_upsert`.

---

## File Structure

```
new_solution/
├── pyproject.toml
├── .env
├── trading_system/
│   ├── __init__.py
│   ├── config.py                    # Settings (DB URL, log level, lookback windows)
│   ├── db/
│   │   ├── __init__.py              # Exports init_db()
│   │   ├── base.py                  # Own Base + TimestampMixin
│   │   ├── models.py               # FactorCache model (27 columns + JSONB)
│   │   └── engine.py               # Imports engine from finance_data, provides session_scope
│   ├── factors/
│   │   ├── __init__.py
│   │   ├── registry.py             # Factor metadata registry
│   │   ├── technical.py            # 13 technical factor functions
│   │   ├── fundamental.py          # 12 fundamental factor functions
│   │   └── utils.py                # safe_div, NaN helpers
│   └── pipeline/
│       ├── __init__.py
│       ├── data_loader.py          # Bulk SQL data loading
│       ├── standardizer.py         # MAD winsorize + z-score
│       ├── writer.py               # bulk_upsert to factor_cache
│       └── orchestrator.py         # Full pipeline: load → compute → standardize → write
├── scripts/
│   ├── init_db.py                  # Create factor_cache table
│   └── calc_factors.py             # CLI: compute factors for a date
├── tests/
│   ├── conftest.py                 # Synthetic data fixtures
│   ├── test_technical.py
│   ├── test_fundamental.py
│   ├── test_standardizer.py
│   ├── test_data_loader.py
│   ├── test_writer.py
│   └── test_orchestrator.py
└── docs/                           # Existing design docs
```

---

## Key Design Decisions

1. **Separate SQLAlchemy Base** — `trading_system` defines its own `declarative_base()`, not importing `finance_data`'s Base. Both coexist in the same DB.
2. **Raw SQL for bulk loading** — `pd.read_sql()` instead of ORM queries for 600K+ row analytical loads.
3. **Per-stock iteration for technical factors** — time-series computation needs history per stock. Cross-sectional for fundamental factors.
4. **Named columns + JSONB** — Named columns for efficient SQL filtering; `factors_json` stores `{"raw": {...}, "zscore": {...}}` for flexibility.
5. **Reuse `finance_data.indicators`** — Delegates to existing `calc_macd`, `calc_adx`, `calc_atr`, `calc_bollinger` instead of reimplementing.
6. **`stock_daily.code` → `factor_cache.stock_code`** — mapping handled in orchestrator.

---

TASKS_PLACEHOLDER

## Task 1: Project Scaffolding

**Files:**
- Create: `new_solution/pyproject.toml`
- Create: `new_solution/.env`
- Create: `new_solution/trading_system/__init__.py`
- Create: `new_solution/trading_system/config.py`
- Create: all `__init__.py` files for subpackages

- [ ] **Step 1:** Create `pyproject.toml` with dependencies: `finance-data` (path dep to `../finance_data`), pandas, numpy, scipy, sqlalchemy, psycopg2-binary, loguru, pydantic-settings. Dev deps: pytest.

- [ ] **Step 2:** Create `.env` with `FINANCE_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/finance`

- [ ] **Step 3:** Create `trading_system/__init__.py` (version string), `config.py` (pydantic Settings class reading .env), and all subpackage `__init__.py` files.

- [ ] **Step 4:** Verify: `cd new_solution && pip install -e . && python -c "from trading_system.config import settings; print(settings.database_url)"`

- [ ] **Step 5:** Commit: `feat: scaffold trading_system project`

---

## Task 2: DB Layer — Base, Model, Engine

**Files:**
- Create: `trading_system/db/base.py`
- Create: `trading_system/db/models.py`
- Create: `trading_system/db/engine.py`
- Create: `trading_system/db/__init__.py`
- Test: `tests/test_db_model.py`

- [ ] **Step 1: Write failing test** — `tests/test_db_model.py`: create FactorCache table in SQLite in-memory, verify all 27+ columns exist, verify composite PK (trade_date, stock_code).

- [ ] **Step 2: Run test, verify FAIL** (`FactorCache` not defined yet)

- [ ] **Step 3: Implement**
  - `db/base.py`: own `Base = declarative_base()` + `TimestampMixin` (same pattern as `finance_data/db/models/base.py`)
  - `db/models.py`: `FactorCache` with 13 technical + 12 fundamental named columns + `factors_json JSONB` + `updated_at`
  - `db/engine.py`: import `engine` from `finance_data.db.engine`, wrap with own `session_scope`
  - `db/__init__.py`: export `init_db()` calling `Base.metadata.create_all(bind=engine)`

- [ ] **Step 4: Run test, verify PASS**

- [ ] **Step 5:** Create `scripts/init_db.py` that calls `init_db()` against live PostgreSQL. Run it: `python scripts/init_db.py`. Verify with `\d factor_cache` in psql.

- [ ] **Step 6:** Commit: `feat: add FactorCache model and DB layer`

---

## Task 3: Factor Registry + Utilities

**Files:**
- Create: `trading_system/factors/registry.py`
- Create: `trading_system/factors/utils.py`
- Test: `tests/test_registry.py`, `tests/conftest.py`

- [ ] **Step 1: Write failing test** — `tests/test_registry.py`: verify `get_all_factor_names()` returns 25 names, `get_factors_by_category("technical")` returns 13, `get_factors_by_category("fundamental")` returns 12.

- [ ] **Step 2: Run test, verify FAIL**

- [ ] **Step 3: Implement**
  - `registry.py`: `FactorCategory` enum, `FactorDef` dataclass, `FACTOR_REGISTRY` dict, `register_factor()`, `get_factors_by_category()`, `get_all_factor_names()`. Register all 25 factors with metadata.
  - `utils.py`: `safe_div(a, b)` returning NaN on zero/None, `require_min_rows(df, n)` validator.
  - `conftest.py`: fixtures generating synthetic OHLCV DataFrame (100 rows, 3 stocks) and synthetic financial_summary DataFrame.

- [ ] **Step 4: Run test, verify PASS**

- [ ] **Step 5:** Commit: `feat: add factor registry and utility helpers`

---

## Task 4: Technical Factors — Momentum, Volatility, Volume

**Files:**
- Create: `trading_system/factors/technical.py`
- Test: `tests/test_technical.py`

- [ ] **Step 1: Write failing tests** — test `momentum_nd` with constant-growth close → exact return; test `volatility_nd` with constant close → 0; test `volume_ratio_5d` with uniform volume → 1.0; test `turnover_deviation` with constant turnover → 0.

- [ ] **Step 2: Run tests, verify FAIL**

- [ ] **Step 3: Implement** `momentum_nd`, `volatility_nd`, `atr_14d` (delegates to `finance_data.indicators.technical.calc_atr`), `volume_ratio_5d`, `turnover_deviation`.

- [ ] **Step 4: Run tests, verify PASS**

- [ ] **Step 5:** Commit: `feat: add momentum, volatility, volume technical factors`

---

## Task 5: Technical Factors — Trend, Relative Strength

**Files:**
- Modify: `trading_system/factors/technical.py`
- Modify: `tests/test_technical.py`

- [ ] **Step 1: Write failing tests** — test `macd_signal` returns Series; test `adx_14d` in [0,100]; test `bb_width > 0` for non-constant series; test `rs_vs_index == 0` when stock=index; test `obv_slope` sign matches price direction.

- [ ] **Step 2: Run tests, verify FAIL**

- [ ] **Step 3: Implement** `macd_signal` (delegates to `calc_macd`, returns DIF), `adx_14d` (delegates to `calc_adx`), `bb_width` (delegates to `calc_bollinger`), `rs_vs_index`, `obv_slope` (OBV then `np.polyfit` rolling).

- [ ] **Step 4: Run tests, verify PASS**

- [ ] **Step 5:** Commit: `feat: add trend and relative strength technical factors`

---

## Task 6: Fundamental Factors — Direct Extraction

**Files:**
- Create: `trading_system/factors/fundamental.py`
- Test: `tests/test_fundamental.py`

- [ ] **Step 1: Write failing tests** — test `get_roe` extracts correct value from summary_df; test handles NaN and Decimal→float; test `get_pe_ttm` with empty valuation_df returns all-NaN.

- [ ] **Step 2: Run tests, verify FAIL**

- [ ] **Step 3: Implement** `get_roe`, `get_gross_margin`, `get_net_margin`, `get_debt_ratio`, `get_revenue_growth`, `get_profit_growth` (all from financial_summary), `get_pe_ttm`, `get_pb`, `get_ps_ttm` (from stock_valuation). Each returns `pd.Series` indexed by stock_code.

- [ ] **Step 4: Run tests, verify PASS**

- [ ] **Step 5:** Commit: `feat: add fundamental factors from summary and valuation`

---

## Task 7: Fundamental Factors — Computed

**Files:**
- Modify: `trading_system/factors/fundamental.py`
- Modify: `tests/test_fundamental.py`

- [ ] **Step 1: Write failing tests** — test `calc_ocf_to_profit` = 1.0 when OCF==NP; test `calc_goodwill_ratio` = 0 when goodwill is None; test `calc_dividend_yield` handles missing price.

- [ ] **Step 2: Run tests, verify FAIL**

- [ ] **Step 3: Implement** `calc_ocf_to_profit(cashflow_df, income_df)`, `calc_accrual_ratio(income_df, cashflow_df, balance_df)`, `calc_goodwill_ratio(balance_df)`, `calc_dividend_yield(dividend_df, valuation_df)`.

- [ ] **Step 4: Run tests, verify PASS**

- [ ] **Step 5:** Commit: `feat: add computed fundamental factors`

---

## Task 8: Standardizer

**Files:**
- Create: `trading_system/pipeline/standardizer.py`
- Test: `tests/test_standardizer.py`

- [ ] **Step 1: Write failing tests** — test `winsorize_mad` clips outlier at 100x median; test `zscore_standardize` mean≈0, std≈1 for normal data; test NaN passthrough; test all-NaN column stays all-NaN.

- [ ] **Step 2: Run tests, verify FAIL**

- [ ] **Step 3: Implement** `winsorize_mad(series, n=3.0)`, `zscore_standardize(series)`, `standardize_factors(df, columns)`.

- [ ] **Step 4: Run tests, verify PASS**

- [ ] **Step 5:** Commit: `feat: add MAD winsorize and z-score standardizer`

---

## Task 9: Data Loader

**Files:**
- Create: `trading_system/pipeline/data_loader.py`
- Test: `tests/test_data_loader.py`

- [ ] **Step 1: Write failing tests** — mock engine with SQLite, insert synthetic stock_daily rows, test `load_daily_prices` returns correct dict structure; test `load_financial_summary` returns latest report per stock.

- [ ] **Step 2: Run tests, verify FAIL**

- [ ] **Step 3: Implement** `FactorDataLoader` with:
  - `load_daily_prices(trade_date, stock_codes)` — bulk SQL `SELECT * FROM stock_daily WHERE trade_date BETWEEN ...`, groupby code
  - `load_index_prices(trade_date, "000300")`
  - `load_financial_summary(trade_date)` — `DISTINCT ON (code) ... ORDER BY code, report_date DESC`
  - `load_financial_statements(trade_date)` — latest income/balance/cashflow per code
  - `load_valuation(trade_date)` — exact date match, empty DF if missing
  - `load_dividends()` — most recent per stock
  - `load_stock_list(exclude_st=True)`

- [ ] **Step 4: Run tests, verify PASS**

- [ ] **Step 5:** Commit: `feat: add bulk data loader for factor pipeline`

---

## Task 10: Writer

**Files:**
- Create: `trading_system/pipeline/writer.py`
- Test: `tests/test_writer.py`

- [ ] **Step 1: Write failing test** — SQLite in-memory FactorCache table, insert records, verify row count; upsert same records with changed values, verify update.

- [ ] **Step 2: Run tests, verify FAIL**

- [ ] **Step 3: Implement** `write_factor_cache(session, records, batch_size=1000)` using PostgreSQL `INSERT ... ON CONFLICT DO UPDATE`. Replicates the `bulk_upsert` pattern from `finance_data.utils`. For SQLite tests, uses simpler insert-or-replace.

- [ ] **Step 4: Run tests, verify PASS**

- [ ] **Step 5:** Commit: `feat: add factor_cache writer with upsert`

---

## Task 11: Pipeline Orchestrator

**Files:**
- Create: `trading_system/pipeline/orchestrator.py`
- Test: `tests/test_orchestrator.py`

- [ ] **Step 1: Write failing test** — integration test with mock `FactorDataLoader` injected, verify `FactorPipeline.run(date)` returns expected record count, verify output contains all 25 factor columns + factors_json.

- [ ] **Step 2: Run tests, verify FAIL**

- [ ] **Step 3: Implement** `FactorPipeline`:
  - `__init__(engine)` — creates loader, logger
  - `_compute_technical_factors(daily_prices, index_prices, trade_date)` — iterates stocks, calls 13 factor functions, assembles cross-sectional DataFrame
  - `_compute_fundamental_factors(summary_df, ...)` — calls 12 factor functions
  - `run(trade_date, stock_codes=None)` — load → compute tech + fundamental → merge → standardize → build factors_json → write
  - `run_range(start_date, end_date)` — loop over trading days

- [ ] **Step 4: Run tests, verify PASS**

- [ ] **Step 5:** Commit: `feat: add factor pipeline orchestrator`

---

## Task 12: CLI Script + End-to-End Test

**Files:**
- Create: `scripts/calc_factors.py`
- Manual test against live DB

- [ ] **Step 1:** Implement CLI with argparse: `--date YYYY-MM-DD`, `--start/--end` for range, `--codes CODE1,CODE2`. Calls `FactorPipeline.run()` or `run_range()`. Logs progress.

- [ ] **Step 2:** Run against live DB: `python scripts/calc_factors.py --date 2026-03-28`

- [ ] **Step 3:** Verify in psql: `SELECT stock_code, momentum_5d, roe, pe_ttm FROM factor_cache WHERE trade_date = '2026-03-28' LIMIT 10`

- [ ] **Step 4:** Run for a date range: `python scripts/calc_factors.py --start 2026-03-01 --end 2026-03-28`

- [ ] **Step 5:** Commit: `feat: add daily factor calculation CLI`

---

## Verification

After all tasks complete:

1. **Unit tests pass:** `cd new_solution && pytest tests/ -v`
2. **Table exists:** `psql -d finance -c "\d factor_cache"` shows all columns
3. **Data populated:** `SELECT COUNT(*) FROM factor_cache WHERE trade_date = '2026-03-28'` returns ~4500+ rows
4. **Factors valid:** `SELECT stock_code, momentum_20d, roe, factors_json->'zscore'->'momentum_20d' FROM factor_cache WHERE trade_date = '2026-03-28' AND stock_code = '600519'` returns non-NULL values
5. **Standardization correct:** `SELECT AVG(momentum_20d), STDDEV(momentum_20d) FROM factor_cache WHERE trade_date = '2026-03-28'` — raw values; z-score values in factors_json should have mean≈0, std≈1
