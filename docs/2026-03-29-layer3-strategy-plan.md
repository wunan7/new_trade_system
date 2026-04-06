# Layer 3: Multi-Strategy Signal Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a multi-strategy signal generation layer that detects market state (6 states), runs 3 stock-picking strategies (value/growth/momentum), dynamically allocates weights, and writes signals to a `signal_history` table.

**Architecture:** Extends `trading_system` at `C:\Users\wunan\projects\new_solution\`. Strategies read pre-computed factors from `factor_cache` (Layer 2 output). A `MarketStateDetector` determines trend+volatility regime from index data. A `SignalGenerator` orchestrator runs strategies, applies market-state-based weights, aggregates multi-strategy signals for the same stock, and writes to DB.

**Tech Stack:** Same as Layer 2 (pandas, numpy, SQLAlchemy 2.0, loguru). No new dependencies.

---

## Context

Layer 2 (factor engine) is complete: 26 factors computed daily into `factor_cache`. Layer 3 consumes those factors to generate trading signals. Event-driven and technical timing strategies are deferred (need `events` table and `trade_constraints` data not yet available).

## File Structure (New Files)

```
trading_system/
├── db/models.py              # MODIFY: add SignalHistory model
├── strategies/
│   ├── __init__.py
│   ├── base.py               # BaseStrategy ABC, Signal dataclass, MarketState enum
│   ├── market_state.py       # MarketStateDetector
│   ├── value.py              # ValueStrategy
│   ├── growth.py             # GrowthStrategy
│   └── momentum.py           # MomentumStrategy
├── signals/
│   ├── __init__.py
│   ├── generator.py          # SignalGenerator orchestrator
│   └── writer.py             # write_signal_history (bulk upsert)
scripts/
└── gen_signals.py            # CLI entry point
tests/
├── test_signal_model.py
├── test_base_strategy.py
├── test_market_state.py
├── test_value_strategy.py
├── test_growth_strategy.py
├── test_momentum_strategy.py
├── test_signal_writer.py
└── test_signal_generator.py
```

## Key Design Decisions

1. **Strategies read factor_cache only** — no raw data loading. All factors pre-computed by Layer 2.
2. **Market state from index data** — CSI300 MA60 trend + volatility ratio. Simplified v1.
3. **Scoring → direction mapping** — Each strategy scores stocks 0-1, maps to direction 0.3-1.0 (all bullish v1, short signals deferred).
4. **Multi-strategy aggregation** — Same stock in multiple strategies → weighted average by market-state weights.
5. **Signal ≠ trade** — All signals recorded (`was_executed=False` default). Layer 4 (risk) decides execution.

## Key Algorithms

### Market State Detection (v1)
```
Trend: CSI300 close vs MA60
  close > MA60 * 1.02 AND momentum_20d > 0 → BULL
  close < MA60 * 0.98 AND momentum_20d < 0 → BEAR
  else → NEUTRAL

Volatility: CSI300 20d vol vs 60d vol
  vol_20d > vol_60d * 1.2 → HIGH
  else → LOW

6 states: BULL_LOW, BULL_HIGH, NEUTRAL_LOW, NEUTRAL_HIGH, BEAR_LOW, BEAR_HIGH
```

### Strategy Scoring
```
Value:    0.30*(1-pb_pct) + 0.30*roe/50 + 0.20*div_yield/0.10 + 0.20*ocf_to_profit/3
Growth:   0.40*profit_g/200 + 0.30*rev_g/100 + 0.20*roe/50 + 0.10*gm/80
Momentum: 0.35*mom20_pct + 0.25*mom60_pct + 0.20*(vol_ratio-0.5)/2.5 + 0.20*adx/60
```

### Weight Table (market_state → strategy allocation)
```
State         | Value | Growth | Momentum | Position Limit
BULL_LOW      |  0.20 |  0.35  |   0.25   | 0.90
BULL_HIGH     |  0.10 |  0.25  |   0.35   | 0.80
NEUTRAL_LOW   |  0.30 |  0.15  |   0.10   | 0.60
NEUTRAL_HIGH  |  0.25 |  0.10  |   0.10   | 0.50
BEAR_LOW      |  0.40 |  0.05  |   0.05   | 0.40
BEAR_HIGH     |  0.30 |  0.00  |   0.00   | 0.20
```

---

## Task 1: SignalHistory DB Model

**Files:**
- Modify: `trading_system/db/models.py`
- Test: `tests/test_signal_model.py`

- [ ] **Step 1: Write failing test** — create SignalHistory in SQLite, verify columns: trade_date, stock_code, strategy, direction, confidence, holding_period, entry_price, stop_loss, take_profit, factors_json, was_executed, filter_reason, llm_override, created_at.

- [ ] **Step 2: Implement** — Add `SignalHistory` model to `db/models.py` using `Base` + `_JSONB` pattern from FactorCache. PK: `id SERIAL`. Indexes on `(stock_code, trade_date)` and `(strategy, trade_date)`. Update `db/__init__.py` init_db if needed.

- [ ] **Step 3: Run test → PASS**

- [ ] **Step 4:** Run `scripts/init_db.py` to create table in PostgreSQL.

- [ ] **Step 5:** Commit: `feat: add SignalHistory model`

---

## Task 2: Base Strategy Interface + Signal Dataclass + MarketState

**Files:**
- Create: `trading_system/strategies/__init__.py`
- Create: `trading_system/strategies/base.py`
- Test: `tests/test_base_strategy.py`

- [ ] **Step 1: Write failing test** — test Signal dataclass fields; test MarketState enum has 6 values; test STRATEGY_WEIGHTS dict has entries for all 6 states.

- [ ] **Step 2: Implement** `strategies/base.py`:
  - `Signal` dataclass: trade_date, stock_code, strategy, direction, confidence, holding_period, entry_price, stop_loss, take_profit, factors (dict)
  - `MarketState` enum: BULL_LOW, BULL_HIGH, NEUTRAL_LOW, NEUTRAL_HIGH, BEAR_LOW, BEAR_HIGH
  - `STRATEGY_WEIGHTS: dict[MarketState, dict]` — the weight table above
  - `BaseStrategy` ABC with `generate(trade_date, factor_df) -> list[Signal]`

- [ ] **Step 3: Run test → PASS**

- [ ] **Step 4:** Commit: `feat: add base strategy interface and market state enum`

---

## Task 3: Market State Detector

**Files:**
- Create: `trading_system/strategies/market_state.py`
- Test: `tests/test_market_state.py`

- [ ] **Step 1: Write failing tests** — test detect with uptrend+low vol → BULL_LOW; test downtrend+high vol → BEAR_HIGH; test neutral → NEUTRAL_LOW.

- [ ] **Step 2: Implement** `MarketStateDetector`:
  - `__init__(engine)` — creates FactorDataLoader
  - `detect(trade_date) -> MarketState` — loads CSI300 index prices (60d lookback), computes MA60, momentum_20d, vol_20d/vol_60d, returns MarketState enum
  - `get_weights(state) -> dict` — returns strategy weights for the given state
  - `get_position_limit(state) -> float` — returns max position ratio

- [ ] **Step 3: Run tests → PASS**

- [ ] **Step 4:** Test against live DB: detect market state for latest date.

- [ ] **Step 5:** Commit: `feat: add market state detector`

---

## Task 4: Value Strategy

**Files:**
- Create: `trading_system/strategies/value.py`
- Test: `tests/test_value_strategy.py`

- [ ] **Step 1: Write failing tests** — test with synthetic factor_df: stock passing all filters gets positive signal; stock failing ROE filter excluded; empty df returns empty list.

- [ ] **Step 2: Implement** `ValueStrategy(BaseStrategy)`:
  - Filters: pb percentile < 30%, roe > 12, dividend_yield > 0.02, debt_ratio < 60
  - Score: 0.30*(1-pb_pct) + 0.30*roe/50 + 0.20*div_yield/0.10 + 0.20*ocf_to_profit/3
  - Direction: 0.3 + 0.7 * normalized_score
  - Confidence: base 0.5, +0.1 if goodwill_ratio < 0.1, +0.1 if accrual_ratio < 0
  - holding_period: 60
  - Top N: 20 stocks max

- [ ] **Step 3: Run tests → PASS**

- [ ] **Step 4:** Commit: `feat: add value strategy`

---

## Task 5: Growth Strategy

**Files:**
- Create: `trading_system/strategies/growth.py`
- Test: `tests/test_growth_strategy.py`

- [ ] **Step 1: Write failing tests** — test high-growth stock passes; test negative growth excluded; test score ranking.

- [ ] **Step 2: Implement** `GrowthStrategy(BaseStrategy)`:
  - Filters: profit_growth > 30, revenue_growth > 20, roe > 8
  - Score: 0.40*profit_g/200 + 0.30*rev_g/100 + 0.20*roe/50 + 0.10*gm/80
  - Direction: 0.3 + 0.7 * normalized_score
  - Confidence: base 0.5, +0.1 if net_margin > 15, +0.1 if revenue_growth > 40
  - holding_period: 60
  - Top N: 20 stocks max

- [ ] **Step 3: Run tests → PASS**

- [ ] **Step 4:** Commit: `feat: add growth strategy`

---

## Task 6: Momentum Strategy

**Files:**
- Create: `trading_system/strategies/momentum.py`
- Test: `tests/test_momentum_strategy.py`

- [ ] **Step 1: Write failing tests** — test top-momentum stock passes; test overheated stock excluded; test OBV confirmation boosts confidence.

- [ ] **Step 2: Implement** `MomentumStrategy(BaseStrategy)`:
  - Filters: momentum_20d percentile >= 80%, momentum_60d percentile >= 70%, momentum_20d <= 0.5, volume_ratio_5d >= 0.5
  - Score: 0.35*mom20_pct + 0.25*mom60_pct + 0.20*(vol_ratio-0.5)/2.5 + 0.20*adx/60
  - Direction: 0.3 + 0.7 * normalized_score
  - Confidence: base 0.5, +0.1 if obv_slope > 0, -0.1 if obv_slope <= 0
  - holding_period: 10
  - Top N: 15 stocks max

- [ ] **Step 3: Run tests → PASS**

- [ ] **Step 4:** Commit: `feat: add momentum strategy`

---

## Task 7: Signal Writer

**Files:**
- Create: `trading_system/signals/__init__.py`
- Create: `trading_system/signals/writer.py`
- Test: `tests/test_signal_writer.py`

- [ ] **Step 1: Write failing test** — insert Signal list into signal_history, verify row count.

- [ ] **Step 2: Implement** `write_signals(session, signals: list[Signal]) -> int`:
  - Convert Signal dataclasses to dicts
  - Use simple INSERT (not upsert — signals are append-only, new id each time)
  - Batch by 500

- [ ] **Step 3: Run tests → PASS**

- [ ] **Step 4:** Commit: `feat: add signal history writer`

---

## Task 8: Signal Generator (Orchestrator) + CLI

**Files:**
- Create: `trading_system/signals/generator.py`
- Create: `scripts/gen_signals.py`
- Test: `tests/test_signal_generator.py`

- [ ] **Step 1: Write failing test** — test with 3 synthetic stocks in factor_cache, verify SignalGenerator.run() returns signals with correct strategy labels.

- [ ] **Step 2: Implement** `SignalGenerator`:
  - `__init__(engine)` — creates MarketStateDetector + strategy instances
  - `_load_factor_df(trade_date) -> pd.DataFrame` — read factor_cache for the date
  - `_aggregate_signals(all_signals, market_state) -> list[Signal]` — weight-merge same-stock signals
  - `run(trade_date, stock_codes=None) -> int` — detect state → run strategies → aggregate → write

- [ ] **Step 3: Implement CLI** `scripts/gen_signals.py`:
  - `--date YYYY-MM-DD`, `--start/--end` for range, `--codes`
  - Logs market state, signal count per strategy

- [ ] **Step 4: Run tests → PASS**

- [ ] **Step 5: E2E test** against live DB: `python scripts/gen_signals.py --date 2026-03-27 --codes 600519,000858,000001`

- [ ] **Step 6:** Commit: `feat: add signal generator orchestrator and CLI`

---

## Verification

1. **All tests pass:** `pytest tests/ -v` — all existing (69) + new tests pass
2. **signal_history populated:** `SELECT COUNT(*), strategy FROM signal_history WHERE trade_date = '2026-03-27' GROUP BY strategy`
3. **Market state detected:** `python -c "from trading_system.strategies.market_state import MarketStateDetector; ..."`
4. **Signal quality:** Verify value signals have roe > 12, momentum signals have high momentum_20d
