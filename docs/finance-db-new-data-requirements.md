# finance 数据库 — 新增数据需求文档

> 基于《A股智能交易决策系统设计文档》，梳理 finance 数据库需要新增的表、字段扩展、采集逻辑
>
> 生成日期：2026-03-29

---

## 目录

- [一、需求总览](#一需求总览)
- [二、新增表详细设计](#二新增表详细设计)
  - [2.1 money_flow 资金流向](#21-money_flow-资金流向)
  - [2.2 trade_constraints 交易约束](#22-trade_constraints-交易约束)
  - [2.3 events 公告事件](#23-events-公告事件)
  - [2.4 macro_data 宏观经济数据](#24-macro_data-宏观经济数据)
  - [2.5 factor_cache 因子缓存](#25-factor_cache-因子缓存)
  - [2.6 signal_history 信号历史](#26-signal_history-信号历史)
  - [2.7 portfolio_positions 持仓记录](#27-portfolio_positions-持仓记录)
  - [2.8 trade_log 交易流水](#28-trade_log-交易流水)
  - [2.9 portfolio_nav 每日净值](#29-portfolio_nav-每日净值)
- [三、已有表修复与扩展](#三已有表修复与扩展)
- [四、数据采集调度整合](#四数据采集调度整合)
- [五、开发优先级与里程碑](#五开发优先级与里程碑)

---

## 一、需求总览

### 新增表清单（9张）

| 表名 | 用途 | 优先级 | 数据源 | 更新频率 | 预估数据量/年 |
|------|------|--------|--------|----------|--------------|
| `money_flow` | 资金流向（北向/主力/融资融券） | **P0** | AKShare | 日级 | ~500万行 |
| `trade_constraints` | 涨跌停价+停牌标记 | **P0** | AKShare | 日级 | ~120万行 |
| `events` | 公告/限售解禁/龙虎榜 | P1 | AKShare/巨潮 | 实时追加 | ~10万行 |
| `macro_data` | GDP/CPI/PMI/社融/M2等 | P1 | AKShare | 月级 | ~500行 |
| `factor_cache` | 因子计算缓存 | P1 | 自计算 | 日级 | ~500万行 |
| `signal_history` | 策略信号记录 | P1 | 自计算 | 日级 | ~5万行 |
| `portfolio_positions` | 持仓记录 | P2 | 系统生成 | 事件触发 | ~200行 |
| `trade_log` | 交易流水 | P2 | 系统生成 | 事件触发 | ~500行 |
| `portfolio_nav` | 每日组合净值 | P2 | 自计算 | 日级 | ~250行 |

### 已有表修改

| 表名 | 修改内容 | 优先级 |
|------|---------|--------|
| `insider_trades` | 修复 code 字段解析bug，清除无效数据，重新采集 | P1 |
| `stock_valuation` | 持续积累历史数据；考虑 Tushare 回补历史 PE/PB | P1 |
| `stock_minute` | 按需采集持仓股分钟K线（API仅近3月） | P2 |

### 与设计文档的映射关系

```
设计文档6层架构  →  finance 数据库需求
─────────────────────────────────────────
第1层 数据采集    →  money_flow, trade_constraints, events, macro_data
第2层 因子计算    →  factor_cache
第3层 策略信号    →  signal_history
第4层 风控仓位    →  portfolio_positions（事前约束读取 trade_constraints）
第5层 LLM融合    →  读取 signal_history + factor_cache（写入由LLM层完成）
第6层 人机交互    →  portfolio_nav, trade_log（回测引擎+面板展示）
```

---

## 二、新增表详细设计

### 2.1 money_flow 资金流向（P0-必须）

> 资金面因子的核心数据源，支撑北向资金、主力资金、融资融券三大类约10个因子的计算。

#### 表结构

```sql
CREATE TABLE money_flow (
    trade_date      DATE NOT NULL,
    code      VARCHAR(10) NOT NULL,
    -- 北向资金
    north_net_buy   NUMERIC(16,4),    -- 北向资金净买入（万元）
    north_hold_pct  NUMERIC(8,4),     -- 北向持仓占流通股比(%)
    -- 主力资金（大单统计）
    main_net_inflow NUMERIC(16,4),    -- 主力净流入（万元）= 超大单+大单净流入
    big_order_ratio NUMERIC(8,4),     -- 大单净流入比(%) = 大单净流入/成交额
    super_big_net   NUMERIC(16,4),    -- 超大单净流入（万元）
    big_net         NUMERIC(16,4),    -- 大单净流入（万元）
    mid_net         NUMERIC(16,4),    -- 中单净流入（万元）
    small_net       NUMERIC(16,4),    -- 小单净流入（万元）
    -- 融资融券
    margin_balance  NUMERIC(16,4),    -- 融资余额（万元）
    margin_buy      NUMERIC(16,4),    -- 融资买入额（万元）
    short_balance   NUMERIC(16,4),    -- 融券余额（万元）
    -- 元数据
    source          VARCHAR(20) DEFAULT 'akshare',
    fetched_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (trade_date, code)
);

-- 索引：按股票查询时间序列
CREATE INDEX idx_money_flow_code ON money_flow(code, trade_date);
```

#### 数据源与采集逻辑

| 数据项 | AKShare 接口 | 说明 |
|--------|-------------|------|
| 北向个股持仓 | `stock_hsgt_hold_stock_em` | 沪股通/深股通持股明细，含持股数量和持股比例 |
| 主力资金流向 | `stock_individual_fund_flow` | 东方财富个股资金流向，含超大/大/中/小单分类 |
| 融资融券个股 | `stock_margin_detail_sse` + `stock_margin_detail_szse` | 沪深交所融资融券明细 |

**采集策略：**
- 每交易日 15:45 启动采集（收盘后数据稳定）
- 北向持仓：全量拉取当日持股清单（约800-1200只），UPSERT入库
- 主力资金：全量拉取当日个股资金流向（~5000只），约60秒完成
- 融资融券：分别拉取沪深两市，合并入库；非两融标的留空
- 增量更新：按 `(trade_date, code)` 主键 UPSERT

**降级方案：**
- 主力资金采集失败 → 当日该字段留NULL，因子计算时标记为缺失
- 北向/融资融券采集失败 → 使用前一日数据，标记 `source='fallback_prev_day'`

#### 因子映射

| 因子名 | 计算逻辑 | 数据字段 |
|--------|---------|---------|
| 北向资金变化 | 今日持仓比-昨日持仓比 | `north_hold_pct` |
| 北向连续流入天数 | `north_net_buy > 0` 连续天数 | `north_net_buy` |
| 主力净流入比 | `main_net_inflow / 当日成交额` | `main_net_inflow` + `stock_daily.amount` |
| 主力连续流入天数 | `main_net_inflow > 0` 连续天数 | `main_net_inflow` |
| 大单占比变化 | 今日大单比-5日均值 | `big_order_ratio` |
| 融资余额变化率 | `(今日-昨日)/昨日` | `margin_balance` |
| 融资买入占比 | `margin_buy / 当日成交额` | `margin_buy` + `stock_daily.amount` |

---

### 2.2 trade_constraints 交易约束（P0-必须）

> 回测引擎的刚性依赖——没有涨跌停价和停牌标记，回测结果不可信。

#### 表结构

```sql
CREATE TABLE trade_constraints (
    trade_date      DATE NOT NULL,
    code      VARCHAR(10) NOT NULL,
    up_limit        NUMERIC(10,4),    -- 涨停价
    down_limit      NUMERIC(10,4),    -- 跌停价
    is_suspended    BOOLEAN DEFAULT FALSE, -- 是否停牌
    is_st           BOOLEAN DEFAULT FALSE, -- 是否ST（冗余，便于快速过滤）
    is_new_stock    BOOLEAN DEFAULT FALSE, -- 是否新股（上市<60交易日）
    fetched_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (trade_date, code)
);

CREATE INDEX idx_tc_code ON trade_constraints(code, trade_date);
```

#### 数据源与采集逻辑

| 数据项 | AKShare 接口 | 说明 |
|--------|-------------|------|
| 涨跌停价 | `stock_zh_a_spot_em` | 东方财富实时行情，含涨停价/跌停价字段 |
| 停牌标记 | `stock_zh_a_spot_em` | 成交量=0且最新价=昨收价判定为停牌 |
| ST标记 | `stock_info.is_st` | 从已有 stock_info 表获取 |
| 新股标记 | `stock_info.list_date` | 上市日期距今<60交易日 |

**采集策略：**
- 每交易日 16:00 采集（与 finance_data 日更错开）
- 从 `stock_zh_a_spot_em` 全量获取一次（该接口已在 stock_valuation 采集中使用，可复用）
- 停牌判定逻辑：`volume == 0 AND close == prev_close`
- is_st / is_new_stock 从已有 stock_info 表计算，无需额外API

**与已有采集的整合：**
- `stock_valuation` 的采集也使用 `stock_zh_a_spot_em`，可在同一次API调用中同时提取涨跌停价字段
- 建议在 `ValuationFetcher` 中扩展，一次采集写两张表，减少API调用

#### 使用场景

| 场景 | 查询逻辑 |
|------|---------|
| 回测：跳过不可交易日 | `WHERE is_suspended = false AND NOT (close >= up_limit OR close <= down_limit)` |
| 事前风控：排除ST | `WHERE is_st = false` |
| 事前风控：排除新股 | `WHERE is_new_stock = false` |

---

### 2.3 events 公告事件（P1-重要）

> 事件驱动策略的核心数据源，捕捉公告/增减持/解禁/龙虎榜等带来的短期定价偏差。

#### 表结构

```sql
CREATE TABLE events (
    id              SERIAL PRIMARY KEY,
    code      VARCHAR(10) NOT NULL,
    event_date      DATE NOT NULL,
    event_type      VARCHAR(50) NOT NULL,
    title           TEXT,
    content         TEXT,
    -- AI 解析字段（由 LLM 后处理填充）
    sentiment       NUMERIC(4,2),      -- 情感分 -1到+1
    impact_strength VARCHAR(10),       -- low/medium/high
    expected_duration INT,             -- 预计影响天数
    -- 元数据
    source          VARCHAR(50),
    raw_url         TEXT,
    fetched_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_events_stock_date ON events(code, event_date);
CREATE INDEX idx_events_type_date ON events(event_type, event_date);
```

#### event_type 枚举与数据源

| event_type | 中文 | AKShare 接口 | 采集频率 |
|-----------|------|-------------|---------|
| `earnings_beat` | 业绩超预期 | `stock_yjyg_em`（业绩预告） | 季报期日更 |
| `earnings_miss` | 业绩不及预期 | `stock_yjyg_em` | 季报期日更 |
| `earnings_report` | 业绩快报 | `stock_yjkb_em`（业绩快报） | 季报期日更 |
| `insider_buy` | 董监高增持 | 修复后的 `stock_inner_trade_xq` | 周更 |
| `insider_sell` | 董监高减持 | 同上 | 周更 |
| `buyback` | 股份回购 | `stock_repurchase_em` | 周更 |
| `equity_incentive` | 股权激励 | `stock_incentive_plan_em` | 月更 |
| `lock_up_expire` | 限售解禁 | `stock_restricted_release_queue_em` | 周更 |
| `block_trade` | 大宗交易 | `stock_dzjy_mdetail` | 日更 |
| `billboard` | 龙虎榜 | `stock_lhb_detail_em` | 日更 |
| `announcement` | 重要公告 | `stock_notice_report`（巨潮） | 日更 |
| `policy_positive` | 政策利好 | TrendRadar 板块信号 + 人工标注 | 事件触发 |
| `policy_negative` | 政策利空 | 同上 | 事件触发 |

**采集策略：**
- 龙虎榜、大宗交易：每交易日 18:30 采集（交易所数据延迟发布）
- 业绩预告/快报：季报期（4/7/8/10月）每日采集
- 限售解禁：每周一采集未来30天解禁计划
- 公告：每交易日 18:30 采集当日重要公告
- AI后处理：`sentiment` / `impact_strength` / `expected_duration` 字段在采集入库后由 LLM 批量填充

**去重规则：** `UNIQUE(code, event_date, event_type, title)` — 同一股票同一天同类型同标题事件不重复入库

---

### 2.4 macro_data 宏观经济数据（P1-重要）

> 市场状态判断器的输入之一，用于判断宏观环境和政策周期。

#### 表结构

```sql
CREATE TABLE macro_data (
    indicator       VARCHAR(50) NOT NULL,
    report_date     DATE NOT NULL,
    value           NUMERIC(16,4),
    yoy_change      NUMERIC(8,4),     -- 同比变化(%)
    mom_change      NUMERIC(8,4),     -- 环比变化(%)
    source          VARCHAR(50) DEFAULT 'akshare',
    fetched_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (indicator, report_date)
);
```

#### indicator 枚举与数据源

| indicator | 中文 | AKShare 接口 | 频率 | 单位 |
|-----------|------|-------------|------|------|
| `gdp` | 国内生产总值 | `macro_china_gdp` | 季度 | 亿元 |
| `cpi` | 居民消费价格指数 | `macro_china_cpi_monthly` | 月度 | % |
| `ppi` | 工业品出厂价格指数 | `macro_china_ppi` | 月度 | % |
| `pmi` | 制造业PMI | `macro_china_pmi` | 月度 | % |
| `pmi_service` | 非制造业PMI | `macro_china_non_man_pmi` | 月度 | % |
| `m2` | 广义货币M2 | `macro_china_money_supply` | 月度 | 亿元 |
| `social_finance` | 社会融资规模 | `macro_china_shrzgm` | 月度 | 亿元 |
| `new_loans` | 新增人民币贷款 | `macro_china_new_financial_credit` | 月度 | 亿元 |
| `shibor_1w` | SHIBOR 1周 | `rate_interbank` | 日度 | % |
| `lpr_1y` | LPR 1年期 | `macro_china_lpr` | 月度 | % |
| `lpr_5y` | LPR 5年期 | `macro_china_lpr` | 月度 | % |
| `usd_cny` | 美元兑人民币 | `fx_spot_quote` | 日度 | 元 |
| `us_10y_yield` | 美国10年期国债收益率 | `bond_zh_us_rate` | 日度 | % |

**采集策略：**
- 每月初（1号或首个交易日）批量更新上月宏观数据
- SHIBOR/汇率/美债收益率：可选日度更新（如需日频宏观因子）
- 历史回补：首次部署时拉取2020年至今的历史数据

**使用场景：**
- 市场状态判断器：PMI > 50 → 扩张期；CPI趋势 → 通胀/通缩判断
- 利率环境：LPR下调 → 利好权益资产；SHIBOR飙升 → 流动性紧张
- 汇率：人民币贬值压力 → 北向资金流出风险

---

### 2.5 factor_cache 因子缓存（P1-重要）

> 第2层因子计算的产出存储，避免每次策略运行重复计算。按日期+股票缓存全部因子值。

#### 表结构

```sql
CREATE TABLE factor_cache (
    trade_date      DATE NOT NULL,
    code      VARCHAR(10) NOT NULL,
    -- 基本面因子（数据源：financial_summary + financial_* 三大报表）
    roe             NUMERIC(8,4),
    roa             NUMERIC(8,4),
    pe_ttm          NUMERIC(10,4),
    pb              NUMERIC(10,4),
    ps_ttm          NUMERIC(10,4),
    dividend_yield  NUMERIC(8,4),
    revenue_growth  NUMERIC(8,4),
    profit_growth   NUMERIC(8,4),
    debt_ratio      NUMERIC(8,4),
    gross_margin    NUMERIC(8,4),
    net_margin      NUMERIC(8,4),
    ocf_to_profit   NUMERIC(8,4),     -- 经营现金流/净利润
    accrual_ratio   NUMERIC(8,4),     -- 应计利润比率
    goodwill_ratio  NUMERIC(8,4),     -- 商誉/净资产
    -- 技术因子（数据源：stock_daily）
    momentum_5d     NUMERIC(8,4),
    momentum_20d    NUMERIC(8,4),
    momentum_60d    NUMERIC(8,4),
    volatility_20d  NUMERIC(8,4),
    volatility_60d  NUMERIC(8,4),
    atr_14d         NUMERIC(12,4),
    volume_ratio_5d NUMERIC(8,4),     -- 5日量比
    turnover_dev    NUMERIC(8,4),     -- 换手率偏离度
    macd_signal     NUMERIC(8,4),
    adx             NUMERIC(8,4),
    bb_width        NUMERIC(8,4),     -- 布林带宽度
    rs_vs_index     NUMERIC(8,4),     -- 相对沪深300强弱
    -- 资金面因子（数据源：money_flow）
    north_flow_chg  NUMERIC(12,4),    -- 北向持仓比变化
    north_days      SMALLINT,         -- 北向连续流入天数
    main_net_ratio  NUMERIC(8,4),     -- 主力净流入比
    margin_chg_rate NUMERIC(8,4),     -- 融资余额变化率
    -- 舆情因子（数据源：finance_public_opinion.ai_analysis_results）
    news_sentiment  NUMERIC(4,2),     -- 板块情绪(-1到+1)
    news_heat       NUMERIC(8,4),     -- 新闻热度指数
    -- 全量因子 JSON（约80个标准化后的因子值）
    factors_json    JSONB,
    -- 元数据
    updated_at      TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (trade_date, code)
) PARTITION BY RANGE (trade_date);

-- 按月分区示例
CREATE TABLE factor_cache_2026_03 PARTITION OF factor_cache
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');
CREATE TABLE factor_cache_2026_04 PARTITION OF factor_cache
    FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
```

#### 数据流

```
数据源表                    →  因子计算引擎  →  factor_cache
────────────────────────────────────────────────────────
stock_daily                →  技术因子(25个)
financial_summary          →  基本面因子(快速路径)
financial_income/balance/  →  基本面因子(深度路径，OCF/NP等)
  cashflow
stock_valuation            →  估值因子(PE/PB/PS分位数)
stock_dividend             →  股息率计算
money_flow                 →  资金面因子(10个)
finance_public_opinion     →  舆情因子(跨库查询)
  .ai_analysis_results
```

**计算时机：** 每交易日 16:30（依赖：stock_daily 18:00日更之前需要前一日数据已就绪；money_flow 15:45采集完成后）

**注意：** 基本面因子无需每日重算——仅在新财报发布后更新。技术因子和资金面因子每日更新。可通过 `updated_at` 判断缓存新鲜度。

---

### 2.6 signal_history 信号历史（P1-重要）

> 记录所有策略产生的信号（不仅是被执行的），用于策略归因、IC评估和实盘/回测对比。

#### 表结构

```sql
CREATE TABLE signal_history (
    id              SERIAL,
    trade_date      DATE NOT NULL,
    code      VARCHAR(10) NOT NULL,
    strategy        VARCHAR(20) NOT NULL,   -- value/growth/momentum/event/technical
    direction       NUMERIC(4,2),           -- -1到+1，正=看多，负=看空
    confidence      NUMERIC(4,2),           -- 0到1
    holding_period  INT,                    -- 建议持仓天数
    entry_price     NUMERIC(12,4),          -- 建议入场价
    stop_loss       NUMERIC(12,4),          -- 建议止损价
    take_profit     NUMERIC(12,4),          -- 建议止盈价
    factors_json    JSONB,                  -- 驱动该信号的关键因子值
    -- 执行追踪
    was_executed    BOOLEAN DEFAULT FALSE,
    filter_reason   VARCHAR(100),           -- 未执行原因：risk_limit/corr_limit/liquidity等
    llm_override    VARCHAR(100),           -- LLM仲裁结果（如有）
    -- 元数据
    created_at      TIMESTAMP DEFAULT NOW()
) PARTITION BY RANGE (trade_date);

-- 按月分区
CREATE TABLE signal_history_2026_03 PARTITION OF signal_history
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');

CREATE INDEX idx_signal_stock_date ON signal_history(code, trade_date);
CREATE INDEX idx_signal_strategy ON signal_history(strategy, trade_date);
```

#### strategy 枚举

| strategy | 对应设计文档 | 信号频率 | 典型holding_period |
|----------|------------|---------|-------------------|
| `value` | 价值策略 | 月度调仓 | 60-120天 |
| `growth` | 成长策略 | 月度调仓 | 60-90天 |
| `momentum` | 动量策略 | 周度调仓 | 5-20天 |
| `event` | 事件驱动 | 事件触发 | 1-10天 |
| `technical` | 技术择时 | 日度 | 作为修正器，无独立持仓期 |

---

### 2.7 portfolio_positions 持仓记录（P2-回测/模拟盘）

```sql
CREATE TABLE portfolio_positions (
    id              SERIAL PRIMARY KEY,
    code      VARCHAR(10) NOT NULL,
    open_date       DATE NOT NULL,
    open_price      NUMERIC(12,4) NOT NULL,
    current_price   NUMERIC(12,4),
    position_pct    NUMERIC(6,4),           -- 仓位占比(0-1)
    shares          INT NOT NULL,           -- 持仓股数
    strategy_source VARCHAR(20) NOT NULL,   -- 来源策略
    signal_id       INT,                    -- 关联 signal_history.id
    stop_loss_price NUMERIC(12,4),
    take_profit_price NUMERIC(12,4),
    max_hold_days   INT,                    -- 最大持仓天数
    status          VARCHAR(10) DEFAULT 'open', -- open/closed
    close_date      DATE,
    close_price     NUMERIC(12,4),
    close_reason    VARCHAR(50),            -- stop_loss/take_profit/time_limit/signal/manual
    pnl_pct         NUMERIC(8,4),           -- 盈亏比例(%)
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_pos_status ON portfolio_positions(status, code);
```

### 2.8 trade_log 交易流水（P2-回测/模拟盘）

```sql
CREATE TABLE trade_log (
    id              SERIAL PRIMARY KEY,
    trade_date      DATE NOT NULL,
    code      VARCHAR(10) NOT NULL,
    direction       VARCHAR(4) NOT NULL,    -- BUY/SELL
    price           NUMERIC(12,4) NOT NULL,
    shares          INT NOT NULL,
    amount          NUMERIC(16,2),          -- price * shares
    strategy        VARCHAR(20),
    signal_id       INT,                    -- 关联 signal_history.id
    position_id     INT,                    -- 关联 portfolio_positions.id
    commission      NUMERIC(10,2),          -- 佣金（万2.5双向）
    stamp_tax       NUMERIC(10,2),          -- 印花税（千1仅卖出）
    slippage        NUMERIC(10,2),          -- 滑点（万2）
    is_paper        BOOLEAN DEFAULT TRUE,   -- true=模拟盘, false=实盘
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_trade_date ON trade_log(trade_date, code);
```

### 2.9 portfolio_nav 每日净值（P2-回测/模拟盘）

```sql
CREATE TABLE portfolio_nav (
    nav_date        DATE PRIMARY KEY,
    total_value     NUMERIC(16,2),    -- 总资产
    cash            NUMERIC(16,2),    -- 现金
    positions_value NUMERIC(16,2),    -- 持仓市值
    position_count  INT,              -- 持仓股票数
    daily_return    NUMERIC(8,6),     -- 当日收益率
    cumulative_return NUMERIC(10,6),  -- 累计收益率
    benchmark_return NUMERIC(8,6),    -- 基准(沪深300)当日收益率
    excess_return   NUMERIC(8,6),     -- 超额收益率
    drawdown        NUMERIC(8,6),     -- 当前回撤
    max_drawdown    NUMERIC(8,6),     -- 历史最大回撤
    sharpe_30d      NUMERIC(8,4),     -- 滚动30日夏普
    is_paper        BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT NOW()
);
```

---

## 三、已有表修复与扩展

### 3.1 insider_trades — 修复 code 字段 Bug（P1）

**现状：** 1,450 行数据全部无效，`code` 字段值为 `000nan` / `00None`。

**根因推测：** `InsiderFetcher` 解析雪球数据时，股票代码为数值型被 pandas 读为 float，格式化6位字符串出错。

**修复方案：**
1. 定位 `InsiderFetcher` 中 code 解析逻辑，确保 `str(int(code)).zfill(6)`
2. 清除无效数据：`DELETE FROM insider_trades WHERE code LIKE '%nan%' OR code LIKE '%None%'`
3. 重新全量采集
4. 修复后可直接供 events 表 `insider_buy`/`insider_sell` 使用

### 3.2 stock_valuation — 历史回补（P1）

**现状：** 仅从 2026-03-10 起积累，历史PE/PB分位数缺少数据。

| 方案 | 内容 | 费用 | 优缺点 |
|------|------|------|--------|
| **A: Tushare回补** | `daily_basic` 接口，回补2020至今 | 200元/年 | 立即可用，约750万行 |
| **B: 自然积累** | 继续日更积累 | 0 | 半年后约60万行，短期不可用 |

**建议：** 先用方案B持续积累，急需时再启用方案A。

### 3.3 stock_minute — 按需采集（P2）

- 仅采集持仓股（5-15只）+ 关注列表的分钟K线
- 周期：5分钟 + 15分钟 + 60分钟
- API仅支持近3个月，不做全量采集

---

## 四、数据采集调度整合

### 完整时间线（已有 ✅ + 新增 🆕）

```
每交易日时间线
─────────────────────────────────────────────────
07:30  🆕 盘前推送（前一日信号 + TrendRadar盘前分析）
09:00  ✅ TrendRadar_Morning（热榜+RSS+AI → finance_public_opinion）
12:30  ✅ TrendRadar_Noon
15:00  收盘
15:45  🆕 采集 money_flow + trade_constraints（可与估值采集合并API）
16:30  🆕 因子计算（→ factor_cache）
17:30  🆕 策略信号生成（→ signal_history）
18:00  ✅ FinanceData_DailyUpdate（日K+估值+指数）
18:30  🆕 采集 events（龙虎榜/大宗交易/公告）
20:00  ✅ TrendRadar_Evening
20:30  🆕 LLM仲裁 + 研报生成 + 推送

每月初  🆕 macro_data 更新
每周一  🆕 限售解禁计划采集
季报期  ✅ 财务数据更新（已有）
周末    🆕 数据校验 + 因子重建 + 周报
```

### 新增 Windows 任务计划

| 任务名 | 时间 | 脚本 |
|--------|------|------|
| `TradingSystem_DataCollect` | 每交易日 15:45 | `scripts/collect_daily.py` |
| `TradingSystem_FactorCalc` | 每交易日 16:30 | `scripts/calc_factors.py` |
| `TradingSystem_SignalGen` | 每交易日 17:30 | `scripts/gen_signals.py` |
| `TradingSystem_EventCollect` | 每交易日 18:30 | `scripts/collect_events.py` |
| `TradingSystem_LLMArbitrage` | 每交易日 20:30 | `scripts/llm_arbitrage.py` |
| `TradingSystem_MacroUpdate` | 每月1日 09:00 | `scripts/collect_macro.py` |
| `TradingSystem_WeeklyCheck` | 每周六 10:00 | `scripts/weekly_check.py` |

---

## 五、开发优先级与里程碑

### Phase 1: 最小可回测版本（P0，约1周）

**目标：** 跑通「数据 → 因子 → 策略信号 → 回测」闭环

| 步骤 | 内容 | 耗时 |
|------|------|------|
| 1 | 创建 `trade_constraints` 表 + 采集器 | 1天 |
| 2 | 创建 `money_flow` 表 + 采集器（主力资金+北向） | 2天 |
| 3 | 创建 `factor_cache` 表 + 基本面/技术因子计算 | 2天 |
| 4 | 创建 `signal_history` 表 + 价值策略/动量策略初版 | 2天 |

**验证标准：** 单策略2020-2026历史回测，输出年化收益/最大回撤/夏普比率。

### Phase 2: 完整策略+风控（P1，约2周）

| 步骤 | 内容 | 耗时 |
|------|------|------|
| 5 | 创建 `events` 表 + 采集器 | 2天 |
| 6 | 修复 `insider_trades` | 0.5天 |
| 7 | 创建 `macro_data` 表 + 采集器 | 1天 |
| 8 | 市场状态判断器 + 策略权重分配 | 2天 |
| 9 | 风控模块（止损止盈/仓位/回撤） | 2天 |
| 10 | 创建 `portfolio_*` + `trade_log` + 回测引擎 | 3天 |

### Phase 3: LLM融合+模拟盘（P2，约2周）

| 步骤 | 内容 | 耗时 |
|------|------|------|
| 11 | LLM信号仲裁Agent | 3天 |
| 12 | 研报生成Agent + 风险预警Agent | 2天 |
| 13 | 模拟盘全流程串联 + 每日推送 | 3天 |
| 14 | 采集调度自动化（Windows任务计划） | 1天 |
| 15 | 3个月模拟盘观察期开始 | — |
