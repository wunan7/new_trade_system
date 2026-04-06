# finance_public_opinion 数据库 — 新增数据需求文档

> 基于《A股智能交易决策系统设计文档》，梳理 TrendRadar 舆情库对接交易系统所需的新增表和接口扩展
>
> 生成日期：2026-03-29

---

## 目录

- [一、现状评估与需求总览](#一现状评估与需求总览)
- [二、新增表设计](#二新增表设计)
- [三、已有表的使用方式与查询接口](#三已有表的使用方式与查询接口)
- [四、MCP Server 扩展](#四mcp-server-扩展)
- [五、开发优先级](#五开发优先级)

---

## 一、现状评估与需求总览

## 一、现状评估与需求总览

### 已有能力（可直接复用，无需改动）

TrendRadar 舆情系统已覆盖交易系统约 80% 的舆情数据需求：

| 已有能力 | 对应表 | 交易系统使用层 |
|---------|-------|--------------|
| 板块影响信号（利多/利空/中性 + 置信度） | `ai_analysis_results.sector_impacts_json` | 第2层舆情因子、第5层LLM融合 |
| 宏观影响分析 | `ai_analysis_results.macro_impact` | 第5层风险预警Agent |
| 风险预警文本 | `ai_analysis_results.risk_alerts` | 第5层风险预警Agent |
| 交易策略建议 | `ai_analysis_results.trading_strategy` | 第5层LLM融合参考 |
| 跨市场联动分析 | `ai_analysis_results.cross_market` | 第5层LLM融合 |
| 政策解读 | `ai_analysis_results.policy_decode` | 第3层事件驱动策略 |
| 新闻热度追踪 | `news_items.crawl_count` + `rank_history` | 第2层热度因子 |
| 新闻分类标签+相关度 | `ai_filter_results.relevance_score` | 个股新闻关联 |
| RSS全球财经 | `rss_items` | 跨市场信号 |
| A股行情快照 | `ai_analysis_results.market_data_snapshot` | 辅助参考 |
| MCP Server（29工具） | `get_market_impact_summary` 等 | Agent工具调用 |

### 能力缺口（需新增开发）

| 缺口 | 当前粒度 | 需求粒度 | 优先级 | 解决方案 |
|------|---------|---------|--------|---------|
| 个股级新闻情感 | 板块级 | 个股级 | **P1** | 新增 `stock_sentiment_daily` 聚合表 |
| 板块→个股映射 | 无 | 需要 | **P1** | 新增 `sector_stock_mapping` 映射表 |
| 个股相关新闻检索 | 手动搜索 | 自动关联 | P2 | 新增 `stock_news_mentions` 关联表 |
| 社交媒体热度 | 未覆盖 | 股吧/雪球 | P3 | 远期考虑，当前TrendRadar以专业财经媒体为主 |
| 研报一致预期 | 未覆盖 | 个股级 | P3 | 需付费数据源，暂不纳入 |

### 核心思路

> **finance_public_opinion 的改动应尽量小** —— TrendRadar 是稳定运行的独立系统，交易系统作为下游消费者，主要通过新增聚合表和查询接口对接，不修改 TrendRadar 的核心采集/分析流程。

---

## 二、新增表设计

### 2.1 sector_stock_mapping 板块股票映射（P1-重要）

> 将 TrendRadar 的板块级信号映射到具体股票，是实现「舆情 → 个股因子」的桥梁。

#### 需求背景

TrendRadar `ai_analysis_results.sector_impacts_json` 产出的信号粒度为板块（如"新能源"、"半导体"），但交易系统的因子计算需要个股粒度。需要一张映射表将板块名称对应到 `finance.stock_info` 的申万行业分类。

#### 表结构

```sql
CREATE TABLE sector_stock_mapping (
    id              SERIAL PRIMARY KEY,
    trendradar_sector VARCHAR(50) NOT NULL,  -- TrendRadar 使用的板块名称
    sw_industry_l1  VARCHAR(50),             -- 对应申万一级行业
    sw_industry_l2  VARCHAR(50),             -- 对应申万二级行业（更精确）
    match_type      VARCHAR(20) NOT NULL,    -- exact/fuzzy/manual
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE(trendradar_sector, sw_industry_l1)
);
```

#### 映射示例

| trendradar_sector | sw_industry_l1 | sw_industry_l2 | match_type |
|-------------------|---------------|----------------|------------|
| 新能源 | 电力设备 | — | manual |
| 半导体 | 电子 | 半导体 | manual |
| 银行 | 银行 | — | exact |
| 石油石化 | 石油石化 | — | exact |
| 计算机 | 计算机 | — | exact |
| 军工 | 国防军工 | — | manual |
| 房地产 | 房地产 | — | exact |
| 医药 | 医药生物 | — | fuzzy |
| 白酒 | 食品饮料 | 白酒 | manual |
| 光伏 | 电力设备 | 光伏设备 | manual |

**维护方式：**
- 初始化：人工整理 TrendRadar 历史出现过的板块名称（约50-80个），逐一映射到申万行业
- 增量：当 LLM 产出新板块名称时，先尝试模糊匹配，匹配不上则标记待人工确认
- 查询 `finance.stock_info` 时通过 `sw_industry_l1` / `sw_industry_l2` 关联到具体股票

#### 使用流程

```
ai_analysis_results.sector_impacts_json
    → 提取 sector 名称
    → 查 sector_stock_mapping 得到 sw_industry
    → 跨库查 finance.stock_info WHERE industry_l1 = sw_industry
    → 得到个股列表
    → 将板块信号分配到个股（作为舆情因子写入 factor_cache）
```

---

### 2.2 stock_sentiment_daily 个股舆情日度聚合（P1-重要）

> 将板块级+新闻级舆情信号聚合为个股粒度的日度因子，供 `finance.factor_cache` 消费。

#### 表结构

```sql
CREATE TABLE stock_sentiment_daily (
    data_date       TEXT NOT NULL,            -- YYYY-MM-DD，与 TrendRadar 保持一致
    stock_code      VARCHAR(10) NOT NULL,
    -- 板块情绪（来源：sector_impacts_json → sector_stock_mapping）
    sector_sentiment NUMERIC(4,2),            -- -1到+1（利空=-1，中性=0，利多=+1，按confidence加权）
    sector_confidence NUMERIC(4,2),           -- 板块信号置信度(0-1)
    sector_source_count INT,                  -- 当日产出该板块信号的分析次数
    -- 新闻热度（来源：news_items + ai_filter_results）
    news_mention_count INT DEFAULT 0,         -- 当日该股相关新闻数
    news_heat_score NUMERIC(8,4),             -- 热度指数（crawl_count加权）
    -- 风险标记（来源：risk_alerts 文本解析）
    has_risk_alert  BOOLEAN DEFAULT FALSE,    -- 当日是否被风险预警提及
    risk_level      VARCHAR(10),              -- low/medium/high
    -- 综合舆情因子（供 factor_cache 直接使用）
    composite_sentiment NUMERIC(4,2),         -- 综合情绪(-1到+1)
    composite_confidence NUMERIC(4,2),        -- 综合置信度(0-1)
    -- 元数据
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (data_date, stock_code)
);

CREATE INDEX idx_ssd_code ON stock_sentiment_daily(stock_code, data_date);
```

#### 计算逻辑

**1. sector_sentiment 计算：**
```python
# 当日所有 ai_analysis_results 中的板块信号
for analysis in today_analyses:
    for impact in json.loads(analysis.sector_impacts_json):
        sector = impact["sector"]
        # 查映射表
        sw_industry = mapping[sector]
        # 查该行业的所有股票
        stocks = get_stocks_by_industry(sw_industry)
        for stock in stocks:
            # 利多=+1, 利空=-1, 中性=0，乘以confidence
            score = {"利多": 1, "利空": -1, "中性": 0}[impact["impact"]]
            sentiment = score * impact["confidence"]
            # 同一股票多次出现取加权平均
```

**2. news_mention_count 计算：**
```python
# 方案1：通过 ai_filter_results 关联（如果配置了个股相关标签）
# 方案2：通过 news_items.title 关键词匹配（股票名称 / 代码）
# 推荐方案1，更准确
```

**3. composite_sentiment 计算：**
```
composite = 0.6 * sector_sentiment + 0.3 * news_heat_normalized + 0.1 * (-risk_flag)
```

**生成时机：** 每交易日 21:00（TrendRadar_Evening 完成后），汇总当日所有分析结果

---

### 2.3 stock_news_mentions 个股新闻关联（P2-增强）

> 记录每条新闻/RSS与具体股票的关联关系，支撑精细化的个股舆情因子。

#### 表结构

```sql
CREATE TABLE stock_news_mentions (
    id              SERIAL PRIMARY KEY,
    data_date       TEXT NOT NULL,
    stock_code      VARCHAR(10) NOT NULL,
    source_type     VARCHAR(10) NOT NULL,     -- hotlist/rss
    source_item_id  INTEGER NOT NULL,          -- news_items.id 或 rss_items.id
    match_method    VARCHAR(20) NOT NULL,      -- keyword/ai_filter/manual
    relevance_score NUMERIC(4,2),              -- 0-1
    sentiment       NUMERIC(4,2),              -- -1到+1（如有，由LLM解析）
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_snm_stock_date ON stock_news_mentions(stock_code, data_date);
CREATE INDEX idx_snm_source ON stock_news_mentions(source_type, source_item_id);
```

#### 数据来源

| match_method | 逻辑 | 精度 | 成本 |
|-------------|------|------|------|
| `keyword` | 新闻标题包含股票简称或代码 | 中（可能误匹配同名） | 零 |
| `ai_filter` | `ai_filter_results` 中已有的标签匹配 | 高（AI分类） | 零（已有） |
| `manual` | 人工标注 | 最高 | 高（不推荐大规模使用） |

**生成时机：** 与 `stock_sentiment_daily` 同步，每交易日 21:00

---

## 三、已有表的使用方式与查询接口

> 以下不新增或修改表结构，仅说明交易系统如何消费已有数据。

### 3.1 ai_analysis_results — 核心舆情信号源

**交易系统消费方式：**

| 字段 | 消费者 | 用途 |
|------|--------|------|
| `sector_impacts_json` | 因子计算层 | → `sector_stock_mapping` → 个股舆情因子 |
| `macro_impact` | 风险预警Agent | 作为LLM Context输入 |
| `risk_alerts` | 风险预警Agent | 触发持仓风险检查 |
| `trading_strategy` | LLM信号仲裁Agent | 作为参考意见之一 |
| `cross_market` | 市场状态判断器 | 外盘联动信号 |
| `policy_decode` | 事件驱动策略 | 政策利好/利空判定 |
| `market_data_snapshot` | 盘前推送 | 行情快照展示 |

**关键查询（供因子计算层使用）：**

```python
def get_today_sector_signals(target_date: str) -> list[dict]:
    """获取当日所有板块信号，按置信度排序"""
    rows = query("""
        SELECT sector_impacts_json, analysis_time
        FROM ai_analysis_results
        WHERE data_date = :d AND success = 1
        ORDER BY id
    """, {"d": target_date})

    signals = []
    for impacts_json, time in rows:
        for s in json.loads(impacts_json):
            s["analysis_time"] = time
            signals.append(s)
    return sorted(signals, key=lambda x: x["confidence"], reverse=True)
```

**关键查询（供风险预警Agent使用）：**

```python
def get_risk_context(target_date: str) -> dict:
    """获取最新的风险上下文，供LLM Agent使用"""
    row = query("""
        SELECT macro_impact, risk_alerts, cross_market, policy_decode,
               trading_strategy, market_data_snapshot
        FROM ai_analysis_results
        WHERE data_date = :d AND success = 1
        ORDER BY id DESC LIMIT 1
    """, {"d": target_date})

    if not row:
        return {"available": False}
    r = row[0]
    return {
        "available": True,
        "macro_impact": r[0],
        "risk_alerts": r[1],
        "cross_market": r[2],
        "policy_decode": r[3],
        "trading_strategy": r[4],
        "market_snapshot": r[5],
    }
```

### 3.2 news_items + rank_history — 新闻热度因子

**用途：** 构建新闻热度指数，热度急升的话题可能影响相关板块/个股。

```python
def get_hot_topics_with_trend(target_date: str, top_n: int = 20) -> list[dict]:
    """获取当日热度最高的话题及其排名趋势"""
    rows = query("""
        SELECT n.id, n.title, n.platform_id, n.rank, n.crawl_count,
               n.first_crawl_time, n.last_crawl_time
        FROM news_items n
        WHERE n.data_date = :d
        ORDER BY n.crawl_count DESC
        LIMIT :n
    """, {"d": target_date, "n": top_n})

    results = []
    for r in rows:
        # 查排名轨迹判断趋势
        ranks = query("""
            SELECT crawl_time, rank FROM rank_history
            WHERE news_item_id = :nid ORDER BY crawl_time
        """, {"nid": r[0]})

        trend = "stable"
        if len(ranks) >= 2:
            if ranks[-1][1] < ranks[0][1]: trend = "rising"
            elif ranks[-1][1] > ranks[0][1]: trend = "falling"
            if ranks[-1][1] == 0: trend = "off_list"

        results.append({
            "title": r[1], "platform": r[2], "rank": r[3],
            "crawl_count": r[4], "trend": trend,
        })
    return results
```

### 3.3 ai_filter_results — 新闻分类关联

**用途：** 将新闻与预定义的关注标签关联，可扩展为个股级关联。

**当前标签体系（ai_filter_tags）：** 约20-30个标签，如"A股大盘走势"、"美联储货币政策"、"AI/大模型"等。

**交易系统扩展建议：** 在 `ai_interests.txt` 中增加个股/行业相关标签，TrendRadar 的 AI 分类功能会自动将新闻匹配到这些标签。无需修改代码，仅修改配置文件即可。

```
# ai_interests.txt 新增示例
贵州茅台/白酒行业
宁德时代/新能源电池
比亚迪/新能源汽车
中芯国际/半导体
...（持仓股 + 关注股）
```

---

## 四、MCP Server 扩展

### 已有可直接使用的工具

| MCP 工具 | 交易系统使用场景 |
|---------|----------------|
| `get_market_impact_summary` | LLM Agent 获取舆情摘要 |
| `get_sector_sentiment` | 查询特定板块情绪 |
| `get_market_snapshot` | 获取A股行情快照 |
| `search_news` | 持仓股相关新闻搜索 |
| `get_latest_rss` | 外盘/全球财经动态 |
| `analyze_topic_trend` | 特定话题的热度趋势 |
| `get_latest_news` | 最新热榜数据 |

### 建议新增的 MCP 工具（3个）

**工具1：`get_stock_sentiment`**
```python
@mcp.tool()
def get_stock_sentiment(stock_code: str, days: int = 7) -> dict:
    """获取个股舆情因子时间序列（读取 stock_sentiment_daily）"""
    # 返回: {dates: [...], sentiment: [...], heat: [...], risk_flags: [...]}
```

**工具2：`get_sector_signal_for_trading`**
```python
@mcp.tool()
def get_sector_signal_for_trading(target_date: str = None) -> list[dict]:
    """获取当日板块信号（已映射到申万行业，可直接对接因子计算）"""
    # 返回: [{sw_industry, impact, confidence, reasoning, stock_count}, ...]
```

**工具3：`get_risk_alerts_for_portfolio`**
```python
@mcp.tool()
def get_risk_alerts_for_portfolio(stock_codes: list[str]) -> dict:
    """检查持仓股是否有相关风险预警"""
    # 遍历当日 risk_alerts + sector_impacts 中的利空信号
    # 返回: {alerts: [{stock_code, risk_type, description, severity}]}
```

---

## 五、开发优先级

### Phase 1: 映射与聚合（P1，约3天）

| 步骤 | 内容 | 耗时 |
|------|------|------|
| 1 | 创建 `sector_stock_mapping` 表 + 初始化映射数据（约60条） | 0.5天 |
| 2 | 创建 `stock_sentiment_daily` 表 + 聚合计算脚本 | 1.5天 |
| 3 | 编写跨库查询接口（finance_public_opinion → finance.factor_cache） | 1天 |

**验证标准：** 给定一只股票代码，能查到当日舆情因子值（sentiment + heat + risk_flag）。

### Phase 2: 精细化关联（P2，约2天）

| 步骤 | 内容 | 耗时 |
|------|------|------|
| 4 | 创建 `stock_news_mentions` 表 + 关键词匹配逻辑 | 1天 |
| 5 | 扩展 `ai_interests.txt` 增加个股标签 | 0.5天 |
| 6 | 新增 3 个 MCP 工具 | 0.5天 |

### Phase 3: LLM Agent 集成（与 finance 库 Phase 3 同步）

| 步骤 | 内容 | 耗时 |
|------|------|------|
| 7 | 风险预警Agent 对接 TrendRadar 数据 | 1天 |
| 8 | LLM信号仲裁Agent 读取舆情Context | 1天 |
| 9 | 盘前/盘后推送整合 TrendRadar 分析报告 | 0.5天 |

---

## 六、跨库数据流总图

```
finance_public_opinion (TrendRadar)          finance (行情+交易系统)
─────────────────────────────────            ──────────────────────────
                                             stock_info (申万行业)
ai_analysis_results ──┐                            ↑
  .sector_impacts_json│                            │
                      ↓                            │
          sector_stock_mapping ─── 申万行业映射 ────┘
                      ↓
          stock_sentiment_daily ──────────→ factor_cache
                      ↑                      .news_sentiment
news_items ───────────┤                      .news_heat
  .crawl_count        │
  .title              │
rank_history ─────────┤
                      │
ai_filter_results ────┘
  .relevance_score

ai_analysis_results ─────────────────────→ LLM 决策融合层 (第5层)
  .macro_impact                              Agent Context
  .risk_alerts
  .trading_strategy
  .cross_market

MCP Server (29+3工具) ───────────────────→ LLM Agent 工具调用
```
