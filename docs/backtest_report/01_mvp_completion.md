# 1. 系统 MVP 达标情况 (2026-04-04)

根据之前[阶段性设计-实现对比表](../阶段性设计-实现对比2026_0401_2230.md)的诊断，在回测之前我们补全了三个关键模块，使系统达到了 MVP 标准：

## 1. 舆情因子接入 (TrendRadar)
- **完成**：注册并对接了 3 个核心舆情因子：
  - `sentiment_score`：来自 AI 分析的综合情感评分（-1 到 +1）
  - `news_heat`：个股新闻热度
  - `news_mention_count`：24小时内新闻提及次数
- **实现方式**：修改 `factors/registry.py` 添加这三个因子的注册，并在 `orchestrator.py` 的计算流水线中通过 `factors.sentiment` 从 `finance_public_opinion.stock_sentiment_daily` 提取 AI 计算好的数据。
- **性能优化**：通过一次性联合查询+单日缓存（_get_cached_sentiment），避免对同一日期的三个因子执行重复的 SQL 连接。

## 2. 事件驱动策略重构 (龙虎榜)
- **完成**：原先的 `strategies/event_driven.py` 每次运行时都实时调用 AKShare 的接口，效率极低且易遭封禁。
- **实现方式**：改为直接从 `finance` 数据库的 `events` 表读取已采集的历史事件，并通过正则表达式从 `content` 字段解析出每日净买入金额。
- **触发条件不变**：个股近 5 天内净买入金额超过 500 万且上榜超过 2 次，即可产生买入信号。

## 3. 市场状态检测器增强
- **确认与集成**：审核了 `strategies/market_state.py`，确认已完整实现了 6 维度的市场状态检测机制，包括：
  1. 趋势 (沪深300 vs MA60 + 动量)
  2. 波动率 (20日 vs 60日)
  3. 市场宽度 (正动量个股比例)
  4. 北向资金 (5日流入趋势)
  5. 换手率分位
  6. 涨跌停比
- **输出状态**：根据这六个维度，系统每天给出一个确定的状态枚举（BULL/NEUTRAL/BEAR x HIGH/LOW），并借此动态调整四类策略的资金分配权重和总仓位限制（通过 `STRATEGY_WEIGHTS`）。
