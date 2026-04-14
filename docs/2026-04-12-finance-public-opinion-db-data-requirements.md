# finance_public_opinion 数据库 —— 数据补充需求文档

**版本**: v1.0  
**日期**: 2026-04-12  
**需求方**: 量化交易系统 (new_trade_system)  
**对接方**: 数据组 / TrendRadar 系统组

---

## 一、现有数据现状速览

| 表名 | 行数 | 日期范围 | 当前质量 |
|------|------|---------|---------|
| news_items | 9,213 | 2025-12-21 ~ 至今 | ⚠️ 大部分平台数据仅到2025-12-27，仅3个平台持续更新 |
| rss_items | 2,521 | 2026-03-21 ~ 至今 | ✅ 正常，6个RSS源持续更新 |
| ai_analysis_results | 33 | 2026-03-22 ~ 至今 | ✅ 每日1-2次，结构完整 |
| ai_filter_results | 1,436 | 2026-03-21 ~ 至今 | ✅ 46个标签，分类正常 |
| stock_sentiment_daily | 30,086 | 2026-03-21 ~ 至今 | ⚠️ 仅20天历史，覆盖约2000-2700只股票/天 |
| stock_news_mentions | 19 | 2026-03-28 ~ 至今 | ❌ 极度稀疏，个股直接提及几乎为空 |
| rank_history | 41,954 | 2025-12-21 ~ 至今 | ✅ 完整 |
| sector_stock_mapping | 39 | — | ✅ TrendRadar→申万映射，39个板块 |

---

## 二、核心诉求背景

量化交易系统当前**完全未使用 TrendRadar 产生的任何 AI 分析数据**，尽管这些数据每日自动生产，是免费且高质量的信号来源。

接入后预期能新增以下能力：
1. **板块情绪因子**：基于 `ai_analysis_results.sector_impacts_json`，每日评估各行业的情绪方向和置信度
2. **个股新闻热度**：基于 `stock_sentiment_daily`，量化个股的新闻关注度
3. **宏观风险感知**：基于 `ai_analysis_results.risk_alerts`，感知系统性风险，辅助仓位决策
4. **LLM 信号仲裁**：基于 `ai_analysis_results.trading_strategy`，为多策略冲突提供参考

---

## 三、需求一：news_items 平台数据恢复（P0 优先级）

### 背景

`news_items` 表中大多数平台的数据**在 2025-12-27 后停止了更新**，只有 3 个平台仍在持续采集：

| 平台 | 最新数据 | 状态 |
|------|---------|------|
| thepaper（澎湃新闻） | 2026-04-11 | ✅ 正常 |
| cls-hot（财联社热榜） | 2026-04-11 | ✅ 正常 |
| wallstreetcn-hot（华尔街见闻） | 2026-04-11 | ✅ 正常 |
| weibo（微博） | 2025-12-27 | ❌ 停止 |
| toutiao（今日头条） | 2025-12-27 | ❌ 停止 |
| baidu（百度新闻） | 2025-12-27 | ❌ 停止 |
| douyin（抖音） | 2025-12-27 | ❌ 停止 |
| bilibili-hot-search（B站） | 2025-12-27 | ❌ 停止 |
| zhihu（知乎） | 2025-12-27 | ❌ 停止 |
| tieba（百度贴吧） | 2025-12-27 | ❌ 停止 |
| ifeng（凤凰新闻） | 2025-12-27 | ❌ 停止 |

### 需求明细

| 项目 | 内容 |
|------|------|
| 恢复采集 | 微博、今日头条、百度新闻、知乎、华尔街见闻（其余可选） |
| 优先恢复 | **财经相关度高的平台**：微博财经、今日头条财经频道、知乎（金融话题） |
| 历史回补 | 2025-12-28 至今（约 3.5 个月缺口） |
| 更新频率 | 维持现有的每日 3 次（09:00 / 12:30 / 20:00）|
| 影响 | 当前 AI 分析输入只有 3 个平台，视野偏窄，影响 `ai_analysis_results` 质量 |

---

## 四、需求二：stock_sentiment_daily 覆盖率提升（P0 优先级）

### 背景

`stock_sentiment_daily` 是量化系统中**情绪因子的核心数据源**，但存在两个关键问题：

1. **历史极短**：仅有 20 天数据（2026-03-21 起），无法评估 IC/IR，也无法用于历史回测
2. **覆盖不稳定**：每日覆盖股票数量从 990（异常低）到 2,735 不等，部分日期大量股票缺失

### 现有字段（已足够，无需新增）

```
data_date, stock_code,
sector_sentiment, sector_confidence, sector_source_count,
news_mention_count, news_heat_score,
has_risk_alert, risk_level,
composite_sentiment, composite_confidence
```

### 需求明细

#### 4.1 历史数据回补

| 项目 | 内容 |
|------|------|
| 目标 | 回补 2025-07-01 至 2026-03-20 的历史舆情因子（约 9 个月，180 个交易日） |
| 方法 | 基于 `news_items`（从 2025-12-21 开始有数据）和 `ai_analysis_results`（2026-03-22 起）做历史推算 |
| 最低要求 | 至少回补至 **2026-01-01**，确保 1 年的有效因子历史 |
| 说明 | 如历史新闻数据不足，可用板块情绪（`sector_sentiment`）作为代理变量，置信度适当降低 |

#### 4.2 覆盖率稳定化

| 项目 | 内容 |
|------|------|
| 目标覆盖 | 每日覆盖 **≥ 3,000 只活跃股票**（当前约 2,000-2,700 只，且不稳定）|
| 缺失股票处理 | 若某只股票无直接新闻提及，以其**申万一级行业**的 `sector_sentiment` 作为默认值，`sector_confidence` 适当折扣（如 × 0.6） |
| 2026-04-08 异常 | 当日仅 990 条（其他日期约 2,500），请检查采集是否有缺失并补全 |

#### 4.3 risk_alert 字段激活

| 项目 | 内容 |
|------|------|
| 当前状态 | `has_risk_alert` 全部为 FALSE，`risk_level` 全部为 "low"，字段未被使用 |
| 需求 | 当 `ai_analysis_results.risk_alerts` 提到某只股票或其所在板块，自动将对应股票的 `has_risk_alert` 设为 TRUE，并填入 `risk_level`（low/medium/high） |
| 预期效果 | 让量化系统在持仓中出现风险股票时能及时感知 |

---

## 五、需求三：ai_analysis_results 频率与字段完善（P1 优先级）

### 背景

`ai_analysis_results` 是系统的**宏观分析核心表**，每日约 1-2 条，质量高，但有以下改进空间：

### 现有字段（已有）

```
data_date, analysis_time, macro_impact, sector_signals,
cross_market, policy_decode, risk_alerts, trading_strategy,
sector_impacts_json, standalone_summaries_json, market_data_snapshot
```

### 需求明细

#### 5.1 新增结构化字段：risk_level

| 项目 | 内容 |
|------|------|
| 新增字段 | `risk_level VARCHAR(10)`（low/medium/high/extreme） |
| 来源 | 由 AI 分析 `risk_alerts` 字段内容，自动判断当日整体市场风险等级 |
| 用途 | 量化系统根据 risk_level 自动调整仓位上限（extreme 时不新开仓） |

#### 5.2 新增结构化字段：market_sentiment_score

| 项目 | 内容 |
|------|------|
| 新增字段 | `market_sentiment_score NUMERIC(4,2)`（-1.0 到 +1.0） |
| 来源 | 综合 `sector_impacts_json` 中各板块情绪（按权重加权平均） |
| 用途 | 作为市场状态检测的情绪维度输入，补充当前 6 维市场状态检测器 |

#### 5.3 更新频率要求

| 项目 | 内容 |
|------|------|
| 当前频率 | 约每日 1-2 次（有时缺失） |
| 目标频率 | **每个交易日至少 1 次**，时间在 20:30-21:30（盘后数据采集完成后） |
| 历史数据 | 当前 33 条（2026-03-22 起），建议持续积累，无需回补（AI 分析依赖实时新闻，无法回填） |

---

## 六、需求四：stock_news_mentions 扩充（P1 优先级）

### 背景

`stock_news_mentions` 表（个股新闻直接提及记录）当前**极度稀疏**：总计仅 19 条，覆盖 19 只股票，且 `sentiment` 字段全部为空。

个股新闻情绪是与板块情绪互补的重要信号——当某只股票被大量个人投资者讨论时，往往意味着短期关注度上升。

### 现有字段

```
data_date, stock_code, source_type, source_item_id,
match_method, relevance_score, sentiment
```

### 需求明细

#### 6.1 扩大个股识别覆盖

| 项目 | 内容 |
|------|------|
| 当前方法 | 仅 "keyword"（关键词匹配），识别率极低 |
| 建议扩展 | 增加股票代码直接提及（如 "000001"、"$平安银行"）+ 公司名称模糊匹配 |
| 目标 | 每日识别 **≥ 100 只**股票的新闻提及（当前约 1-2 只/天） |

#### 6.2 填充 sentiment 字段

| 项目 | 内容 |
|------|------|
| 当前状态 | `sentiment` 字段全为 NULL |
| 需求 | 对识别到的个股提及，通过 AI 分析新闻标题（title 字段）判断情感极性（正/中/负），填入 `sentiment`（-1 到 +1） |
| 方法 | 可复用 TrendRadar 现有 AI 分析能力，批量处理 |

---

## 七、需求五：新增 rss_feeds（P2 优先级）

### 背景

当前 RSS 订阅源（6 个）以**境外财经媒体**为主（Reuters、FT、CNBC、WSJ、Yahoo），缺乏 A 股专项财经信息源，影响 A 股相关新闻的覆盖质量。

### 建议新增 RSS 源

| 来源 | 类型 | 内容 | 重要性 |
|------|------|------|--------|
| 财联社 RSS | 国内财经 | A 股实时资讯、政策解读 | 🔴 高 |
| 新浪财经 RSS | 国内财经 | 市场动态、个股公告 | 🟡 中 |
| 东方财富 RSS | 国内财经 | 研报摘要、机构动态 | 🟡 中 |
| 国家统计局 RSS | 官方数据 | PMI、CPI 等数据发布 | 🟡 中 |
| 中国人民银行 RSS | 货币政策 | 利率决议、货币政策 | 🟡 中 |

---

## 八、优先级汇总

| 优先级 | 需求 | 预估工作量 | 预期收益 |
|--------|------|----------|---------|
| **P0** | 恢复 8 个平台的 news_items 持续采集 | 1-2 天 | AI 分析输入更全面，情绪因子质量提升 |
| **P0** | stock_sentiment_daily 覆盖率 ≥3000只/天 + 历史回补至 2026-01-01 | 3-5 天 | 情绪因子可用于实盘，IC/IR 可评估 |
| **P1** | ai_analysis_results 新增 risk_level + market_sentiment_score 字段 | 1-2 天 | 支持系统性风险感知和市场状态6维检测 |
| **P1** | stock_news_mentions 扩大覆盖（≥100只/天）+ sentiment 填充 | 3-4 天 | 个股情绪因子可用，补充板块情绪 |
| **P1** | stock_sentiment_daily risk_alert 字段激活 | 1 天 | 持仓风险预警能力 |
| **P2** | 新增 A 股专项 RSS 源（财联社/新浪财经等） | 1 天 | 提升 A 股新闻覆盖深度 |

---

## 九、与量化系统的对接说明

数据补充完成后，量化系统将通过以下方式消费数据：

### 接口1：板块情绪因子

```sql
-- 交易系统每日 19:30 查询
SELECT data_date, stock_code, composite_sentiment, composite_confidence
FROM stock_sentiment_daily
WHERE data_date = [T-1 交易日]
-- 映射：stock_code → sector → factor_cache.sentiment_score
```

### 接口2：市场整体情绪（市场状态6维之一）

```sql
-- 从 ai_analysis_results 获取当日市场情绪评分
SELECT market_sentiment_score, risk_level
FROM ai_analysis_results
WHERE data_date = [T-1 交易日]
ORDER BY analysis_time DESC LIMIT 1
```

### 接口3：板块信号（事件驱动增强）

```sql
-- 获取今日看多板块
SELECT sector, impact, confidence, reasoning
FROM (
    SELECT jsonb_array_elements(sector_impacts_json::jsonb) AS elem
    FROM ai_analysis_results
    WHERE data_date = [T-1 交易日]
    ORDER BY analysis_time DESC LIMIT 1
) t
WHERE elem->>'impact' = '利多' AND (elem->>'confidence')::float > 0.75
```

---

*文档生成：2026-04-12 | 需求方：量化交易系统组 | 数据来源：数据库现状探查*
