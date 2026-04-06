# 2. 数据缺失的根本原因与影响链

## 2.1 数据缺失的发现过程

### 初始症状
在第一版 3 年回测中，我们观察到两个异常现象：
1. **2024 年全年零交易**：系统在 2023 年底后完全停止交易，净值曲线变成一条水平线。
2. **价值策略几乎消失**：在 3 年 3469 次买入中，价值策略仅触发了 **13 次**（0.4%），而动量策略占据了 84.6%。

### 排查路径

#### 第一层：风控死锁
最初怀疑是风控系统过于严格。检查 `drawdown_monitor.py` 后发现：
```python
def allows_new_positions(self) -> bool:
    return self.level == DrawdownLevel.NORMAL  # 只要回撤>8%就永久禁止开仓
```
这个设计在 2023 年底系统回撤达到 8% 后，触发了 `YELLOW` 级别，从此禁止所有新仓位。由于不买入新股票，净值永远停留在底部，回撤永远保持在 8% 以上，形成了**死锁**。

**修复**：放宽阈值至 12%/15%/20%/25%，并改为"限制仓位上限"而非"完全禁止开仓"。

#### 第二层：策略失衡
解除死锁后，系统恢复了交易，但价值策略的信号数依然极少（13 次）。这不符合设计预期——在 `bear_low` 和 `neutral_low` 状态下，价值策略应该占据 30% 的权重。

检查价值策略的选股逻辑（`strategies/value.py`）：
```python
def generate_signals(self, factor_df: pd.DataFrame, ...) -> list[Signal]:
    # 筛选条件
    mask = (
        (factor_df['pe_ttm'] < factor_df['pe_ttm'].quantile(0.3)) &  # PE < 30分位
        (factor_df['pb'] < factor_df['pb'].quantile(0.3)) &          # PB < 30分位
        (factor_df['dividend_yield'] > factor_df['dividend_yield'].quantile(0.7))  # 股息率 > 70分位
    )
```

#### 第三层：因子数据缺失
检查 `factor_cache` 表中 2023-2024 年的数据：
```sql
SELECT trade_date, 
       COUNT(*) as total,
       COUNT(pe_ttm) as pe_count,
       COUNT(pb) as pb_count,
       COUNT(dividend_yield) as div_count
FROM factor_cache
WHERE trade_date BETWEEN '2023-04-03' AND '2024-12-31'
GROUP BY trade_date;
```

**结果**：`pe_count = 0`, `pb_count = 0`, `div_count = 0`。

所有估值因子在 2023-2024 年间全部为 NULL！

#### 第四层：底层数据源缺失
追溯到 `finance` 数据库的 `stock_valuation` 表：
```sql
SELECT MIN(trade_date), MAX(trade_date), COUNT(*)
FROM stock_valuation
WHERE trade_date BETWEEN '2023-01-01' AND '2025-06-30';
```

**结果**：`COUNT(*) = 0`。

根本原因找到了：`finance_data` 数据采集项目在 2023-2025 年间**从未采集过 `stock_valuation` 表的数据**。这张表包含了每日全市场股票的 PE、PB、PS、股息率、市值等关键估值指标。

## 2.2 数据缺失的影响链

```
底层数据源缺失 (stock_valuation 表 2023-2025 年为空)
    ↓
因子计算引擎无法生成估值因子 (pe_ttm, pb, dividend_yield 全为 NULL)
    ↓
factor_cache 表中估值列全为空
    ↓
价值策略的筛选条件永远不满足 (NULL < quantile(0.3) 永远为 False)
    ↓
价值策略 3 年仅触发 13 次信号 (应该是 500+ 次)
    ↓
系统被迫单腿依赖动量策略 (84.6% 占比)
    ↓
动量策略在震荡/熊市中频繁追涨杀跌
    ↓
胜率低 (34.15%)、盈亏比差 (0.86)、回撤大 (21.84%)
    ↓
3 年总收益 -19.86%，跑输基准 28.42%
```

## 2.3 其他数据问题

### 资金面因子的部分缺失
在排查过程中还发现了 `money_flow` 表的两个问题：

1. **`north_net_buy` 字段全为 NULL**
   - 影响：无法计算北向资金净买入强度 (`north_flow_chg`) 和净买入天数占比 (`north_days`)。
   - 解决方案：使用 `north_hold_pct`（北向持仓比例）的变动作为替代指标。公式：
     ```python
     north_flow_chg = (current_north_hold_pct - prev_north_hold_pct) / 100
     ```
   - 经济学等价性：持仓比例的变动 = 买入股数 / 总股本 ≈ 买入净额 / 流通市值。

2. **2026年3月底后 `main_net_inflow` 和 `margin_balance` 断更**
   - 影响：3月28日后主力资金和融资融券数据缺失。
   - 状态：数据采集组已修复，4月1日后数据恢复正常。

### 舆情因子的时间窗口限制
`stock_sentiment_daily` 表仅从 2026-03-21 开始有数据，这意味着：
- 2023-2025 年的回测中，舆情因子（`sentiment_score`, `news_heat`, `news_mention_count`）全部为空。
- 但由于舆情因子在策略权重中占比较小（主要用于辅助过滤），对整体回测结果影响有限。

## 2.4 数据补全方案

### 执行步骤
1. **需求文档输出**：编写了 `docs/valuation_data_backfill_requirement.md`，明确了补全的时间范围（2020-01-01 至 2025-06-30）、目标字段（pe_ttm, pb, ps_ttm, circulating_market_cap, total_market_cap）和数据源建议（Tushare Pro 的 `daily_basic` 接口）。

2. **数据采集组执行**：数据采集组使用 Tushare Pro 批量拉取了 2023-2026 年的历史估值数据，共 785 个交易日，数百万条记录。

3. **因子重算**：编写 `recompute_factors.py` 脚本，遍历 716 个交易日，逐日重新计算因子并覆盖写入 `factor_cache`。耗时约 12 小时（平均 60 秒/天）。

4. **验证**：
   ```sql
   SELECT COUNT(pe_ttm), COUNT(pb), COUNT(ps_ttm)
   FROM factor_cache
   WHERE trade_date BETWEEN '2023-04-03' AND '2026-04-03';
   ```
   结果：所有估值因子字段的非空记录数达到数百万条，覆盖率接近 100%。

## 2.5 经验教训

1. **数据完整性是量化系统的基石**：在多因子、多策略系统中，任何一个关键因子的缺失都可能导致某个策略完全失效，进而影响整体表现。

2. **回测前必须进行数据质量检查**：在启动长周期回测前，应该先对 `factor_cache` 进行抽样检查，确认关键因子（尤其是估值、资金面）的覆盖率。

3. **策略失衡是数据问题的早期信号**：当某个策略的信号数远低于预期时（如价值策略 3 年仅 13 次），应该立即排查底层数据，而不是调整策略参数。

4. **建立数据监控机制**：在每日定时任务中，应该增加对关键表（`stock_valuation`, `money_flow`, `stock_sentiment_daily`）的数据完整性监控，一旦发现某天的记录数异常（如从 5000+ 骤降至 2000+），立即告警。
