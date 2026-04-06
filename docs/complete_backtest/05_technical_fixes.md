# 5. 技术修复记录

本文档记录了在回测过程中发现并修复的所有代码级别 Bug。

## 5.1 舆情因子注册缺失

**文件**：`trading_system/factors/registry.py`

**问题**：`sentiment.py` 中实现了 3 个舆情因子（sentiment_score, news_heat, news_mention_count），`orchestrator.py` 也调用了它们，但 `registry.py` 中没有注册。导致这些因子不会出现在 `get_all_factor_names()` 的返回值中。

**修复**：在 `registry.py` 末尾添加：
```python
# Sentiment (3)
register_factor("sentiment_score", FactorCategory.SENTIMENT, ...)
register_factor("news_heat", FactorCategory.SENTIMENT, ...)
register_factor("news_mention_count", FactorCategory.SENTIMENT, ...)
```

## 5.2 事件驱动策略重构

**文件**：`trading_system/strategies/event_driven.py`

**问题**：原实现每次调用 `generate()` 时都通过 AKShare 实时拉取龙虎榜数据，效率低且可能触发 API 限流。同时 `finance.events` 表中已有 694 条龙虎榜历史记录未被利用。

**修复**：重构为从 `finance.events` 表查询最近 5 天的龙虎榜记录，用正则表达式从 `content` 字段解析净买入金额（`净买入: ([-\d.]+)万元`），移除了对 AKShare 的运行时依赖。

## 5.3 全 NaN Series 过滤失效

**文件**：`trading_system/pipeline/orchestrator.py`

**问题**：`_compute_money_flow_factors()` 和 `_compute_sentiment_factors()` 中，当底层数据缺失时，返回的 DataFrame 包含有索引但全为 NaN 的 Series。原过滤逻辑：
```python
factors = {k: v for k, v in factors.items() if not v.empty}
```
`pd.Series(index=[...], dtype=float)` 的 `.empty` 属性为 `False`（因为有索引），导致全 NaN 数据被合并进最终的 DataFrame，占用了列位但不提供任何有效信息。

**修复**：
```python
factors = {k: v for k, v in factors.items() if not v.empty and v.notna().any()}
```

## 5.4 sentiment.py 查询效率与容错

**文件**：`trading_system/factors/sentiment.py`

**问题**：
1. 三个函数各自独立连接 `finance_public_opinion` 数据库查同一张表，效率低。
2. 当 `stock_sentiment_daily` 无数据时，返回有索引但全 NaN 的 Series（同 5.3 的问题）。

**修复**：
- 合并为一次查询，缓存结果供三个函数复用。
- 无数据时返回真正的空 Series（`pd.Series(dtype=float)`）。
- 有数据但全 NaN 时也返回空 Series。

## 5.5 data_loader 缺少 north_hold_pct 和 circulating_market_cap

**文件**：`trading_system/pipeline/data_loader.py`

**问题**：
1. `load_valuation()` 的 SQL 未包含 `circulating_market_cap` 字段。
2. `load_money_flow()` 的 SQL 未包含 `north_hold_pct` 字段。
3. 存在两处 SQL 定义（一处在方法开头用于无日期范围查询，一处在中间用于带日期范围查询），后者覆盖了前者。

**修复**：在两处 SQL 中都添加了缺失字段。

## 5.6 北向资金因子改用 north_hold_pct 近似

**文件**：`trading_system/factors/money_flow.py`

**问题**：`money_flow` 表中 `north_net_buy` 字段全为 NULL（上游数据源无法提供），导致 `calc_north_flow_chg()` 和 `calc_north_days()` 永远返回空值。

**修复**：改用 `north_hold_pct`（北向持仓比例）的日间变动来近似：
```python
# calc_north_flow_chg: 5日持仓比例变动
north_flow_chg = (current_north_hold_pct - prev_5d_north_hold_pct) / 100

# calc_north_days: 20日内持仓比例上升的天数占比
north_days = count(daily_pct_change > 0) / total_days
```

经济学等价性：持仓比例变动 ≈ 净买入额 / 流通市值，在个股层面是合理的近似。

## 5.7 回测引擎缺少事件驱动策略

**文件**：`trading_system/backtest/engine.py`

**问题**：`BacktestEngine.__init__()` 中只注册了 3 个策略（value, growth, momentum），缺少 event_driven。同时 `_load_factor_df()` 的 SQL 未包含 3 个舆情因子列。

**修复**：
```python
self.strategies = {
    "value": ValueStrategy(),
    "growth": GrowthStrategy(),
    "momentum": MomentumStrategy(),
    "event": EventDrivenStrategy(engine),  # 新增
}
```
SQL 中添加 `sentiment_score, news_heat, news_mention_count`。

## 5.8 entry_price 为 None 导致比较异常

**文件**：`trading_system/backtest/engine.py`

**问题**：事件驱动策略生成的 Signal 对象 `entry_price` 为 `None`，在回测引擎中执行 `sig.entry_price <= 0` 时抛出 `TypeError`。

**修复**：
```python
if (sig.entry_price is None or sig.entry_price <= 0) and sig.stock_code in prices:
    sig.entry_price = prices[sig.stock_code]
```

## 5.9 风控死锁（DrawdownMonitor）

**文件**：`trading_system/risk/drawdown_monitor.py`

**问题**：原设计中回撤阈值过于激进：
- YELLOW（8%）：禁止所有新仓位
- CIRCUIT_BREAK（18%）：全部平仓

当系统回撤达到 8% 后，`allows_new_positions()` 返回 `False`，禁止开新仓。由于不买入新股票，净值无法恢复，回撤永远保持在 8% 以上，形成死锁。

**修复**：
1. 放宽阈值：YELLOW 12% → ORANGE 15% → RED 20% → CIRCUIT_BREAK 25%
2. 改变逻辑：除 CIRCUIT_BREAK 外，所有级别都允许开新仓，但通过 `position_limit_override` 限制总仓位上限。
```python
def allows_new_positions(self) -> bool:
    return self.level != DrawdownLevel.CIRCUIT_BREAK  # 仅熔断时禁止
```

## 5.10 position_sizer 中 NaN 价格导致崩溃

**文件**：`trading_system/risk/position_sizer.py`

**问题**：部分股票（停牌股）的 `entry_price` 为 0.0 或 NaN，传入 `_round_to_lot()` 后导致 `math.floor(NaN)` 抛出 `ValueError: cannot convert float NaN to integer`。

**修复**：
1. 在 `size()` 方法入口处过滤无效信号：
```python
if pd.isna(sig.entry_price) or sig.entry_price <= 0:
    logger.warning(f"Skipping {sig.stock_code}: invalid entry_price")
    continue
```
2. 在 `_round_to_lot()` 中增加 try-except 兜底：
```python
try:
    if pd.isna(price) or pd.isna(pct) or pd.isna(total_value) or price <= 0:
        return 0
    ...
except (ValueError, TypeError):
    return 0
```

## 5.11 修复总结

| # | 问题 | 严重程度 | 影响范围 |
|---|------|---------|---------|
| 5.1 | 舆情因子未注册 | 中 | 因子不参与标准化和评估 |
| 5.2 | 事件策略依赖外部 API | 中 | 回测效率和稳定性 |
| 5.3 | 全 NaN 过滤失效 | 高 | 资金面和舆情因子全部丢失 |
| 5.4 | sentiment.py 效率低 | 低 | 每日多次重复查询 |
| 5.5 | data_loader 字段缺失 | 高 | 北向资金和市值数据无法加载 |
| 5.6 | north_net_buy 无数据 | 高 | 2 个资金面因子完全失效 |
| 5.7 | 回测缺少事件策略 | 中 | 事件驱动策略不参与回测 |
| 5.8 | entry_price 为 None | 高 | 回测崩溃 |
| 5.9 | 风控死锁 | **致命** | 系统永久停止交易 |
| 5.10 | NaN 价格崩溃 | 高 | 回测崩溃 |

其中 **5.9（风控死锁）** 是最严重的问题，它直接导致了第一版回测中 2024 年全年零交易的现象。
