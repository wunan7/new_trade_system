# finance 数据库 —— 数据补充需求文档

**版本**: v1.0  
**日期**: 2026-04-12  
**需求方**: 量化交易系统 (new_trade_system)  
**对接方**: 数据组

---

## 一、现有数据现状速览

| 表名 | 行数 | 日期范围 | 当前质量 |
|------|------|---------|---------|
| stock_daily | ~665万 | 2020-01-02 ~ 至今 | ✅ 完整，每日自动更新 |
| stock_valuation | ~充足 | **2020-01-02 ~ 至今** | ✅ 历史完整（6年） |
| financial_summary | 15万+ | 2015 ~ 2025-Q3 | ✅ 完整 |
| financial_income/balance/cashflow | 各8万+ | 2015 ~ 2025-Q3 | ✅ 完整 |
| money_flow | ~90万 | 2025-07-23 ~ 至今 | ⚠️ 多列为空，见下文 |
| events | 96,207 | 2020-01-02 ~ 至今 | ⚠️ 仅有龙虎榜类型 |
| macro_data | 1,967 | 各指标不同 | ⚠️ 指标不全，部分滞后 |
| trade_constraints | 46,701 | **仅 2026-03-27 ~ 至今（9天）** | ❌ 历史严重不足 |
| insider_trades | 17,839 | 2026-03-29 一次性采集 | ❌ 历史严重不足 |
| factor_cache | ~366万 | 2023-04-03 ~ 至今 | ✅ 43因子，系统自动维护 |

---

## 二、需求一：money_flow 字段补全（P0 优先级）

### 背景

`money_flow` 表当前每日更新，但多个核心字段**全部为空**（以 2026-04-09 为例，5203 条记录）：

| 字段 | 当前非空率 | 描述 |
|------|----------|------|
| north_net_buy | **0%** | 北向净买入金额（万元） |
| north_hold_pct | 53.2% | 北向持股比例（%）— 仅约800只沪深港通标的 |
| main_net_inflow | 99.7% | ✅ 主力净流入（万元）— 基本正常 |
| super_big_net | 99.7% | ✅ 超大单净流入（万元）— 基本正常 |
| big_order_ratio | **0%** | 大单占比（%） |
| margin_balance | **0%** | 融资余额（万元） |
| margin_buy | **0%** | 融资买入额（万元） |
| short_balance | **0%** | 融券余额（万元） |

另外，`north_hold_pct` 的历史数据仅从 **2026-03-26** 开始，而 `money_flow` 表的整体数据从 2025-07-23 开始，存在大量历史缺口。

### 需求明细

#### 2.1 补全 north_net_buy（北向净买入金额）

| 项目 | 内容 |
|------|------|
| 字段 | `north_flow.north_net_buy`（万元） |
| 覆盖股票 | 沪深港通标的（约 800-1000 只，沪股通 + 深股通） |
| 历史回填 | 2022-01-01 至今（3年以上） |
| 日频更新 | 每个交易日收盘后（16:00前） |
| 数据来源 | AKShare `stock_hsgt_hold_stock_em` 或同类接口 |

#### 2.2 补全融资融券数据

| 项目 | 内容 |
|------|------|
| 字段 | `margin_balance`（融资余额）、`margin_buy`（融资买入额）、`short_balance`（融券余额） |
| 覆盖股票 | 全市场融资融券标的（约 3000 只） |
| 历史回填 | 2022-01-01 至今 |
| 日频更新 | 每个交易日 |
| 数据来源 | AKShare `stock_margin_sse_em`、`stock_margin_szse_em` |

#### 2.3 补全大单占比字段

| 项目 | 内容 |
|------|------|
| 字段 | `big_order_ratio`（大单净流入占成交额比%） |
| 说明 | 当前 `super_big_net` 和 `big_net` 已有数据，只需补充其比率字段 |
| 建议 | 可由系统自行从已有字段计算：`(super_big_net + big_net) / stock_daily.amount * 100` |

#### 2.4 补全 north_hold_pct 历史数据

| 项目 | 内容 |
|------|------|
| 字段 | `north_hold_pct`（北向持股比例%） |
| 当前状态 | 仅从 2026-03-26 开始（约 12 个交易日） |
| 历史回填 | 2022-01-01 至今（3年以上） |
| 数据来源 | AKShare `stock_hsgt_hold_stock_em` |

---

## 三、需求二：trade_constraints 历史回填（P0 优先级）

### 背景

`trade_constraints` 表（涨跌停价格 + 停牌标记）**仅有 9 天数据**（2026-03-27 起），严重影响回测的真实性——当前回测中会在涨停板买入、跌停板卖出，产生无法执行的虚假交易记录。

### 需求明细

| 项目 | 内容 |
|------|------|
| 字段 | `up_limit`（涨停价）、`down_limit`（跌停价）、`is_suspended`（是否停牌）、`is_st`（是否ST）、`is_new_stock`（是否次新股，上市<60交易日） |
| 覆盖股票 | 全市场所有股票（5000+） |
| 历史回填范围 | **2020-01-01 至今**（与 stock_daily 对齐） |
| 日频更新 | 每个交易日盘后（15:30-16:00） |
| 数据来源 | AKShare `stock_zh_a_spot_em`（实时行情含涨跌停价）或 `stock_zh_limit_up_em`、`stock_zh_limit_down_em` |
| 优先级 | **P0**，当前停牌数据仅 1,693 条 / 9天，无法覆盖历史 |

---

## 四、需求三：insider_trades 历史扩充（P1 优先级）

### 背景

`insider_trades` 表（董监高交易记录）仅在 2026-03-29 做过一次性采集（17,839 条），只反映了当时的历史，**缺少 2026-03-29 之后的持续更新机制**，且字段结构已确认正常（代码字段无bug）。

### 现有字段

```
code, trade_date, insider_name, insider_title, relation,
direction（增持/减持）, transaction_shares, transaction_price,
transaction_value, shares_after, change_ratio
```

### 需求明细

| 项目 | 内容 |
|------|------|
| 历史覆盖 | 2020-01-01 至今（与 stock_daily 对齐） |
| 持续更新 | 每周更新一次（董监高交易信息通常T+2披露） |
| 数据来源 | AKShare `stock_zh_inst_managers_trade_em` 或同类接口 |
| 预期用途 | 事件驱动策略的信号来源（高管增持 = 正面信号，大额减持 = 负面信号） |
| 已有数据 | 保留现有 17,839 条，仅补充缺失时段 |

---

## 五、需求四：macro_data 指标扩充与及时更新（P1 优先级）

### 背景

`macro_data` 表已建，现有 6 个指标，但**缺少对交易系统最关键的指标**，且部分指标数据截止到 2025-08（已滞后 8 个月）。

### 现有指标状态

| 指标 | 行数 | 最新数据 | 状态 |
|------|------|---------|------|
| CPI_YEARLY | 475 | 2025-08-09 | ❌ 滞后8个月 |
| PPI_YEARLY | 361 | 2025-08-09 | ❌ 滞后8个月 |
| CPI_MONTHLY | 354 | 2025-08-09 | ❌ 滞后8个月 |
| M2_YEARLY | 337 | 2025-08-13 | ❌ 滞后8个月 |
| PMI_SERVICE | 220 | 2026-03-01 | ⚠️ 略滞后 |
| PMI_MFG | 220 | 2026-03-01 | ⚠️ 略滞后 |

### 需求明细

#### 5.1 补全现有指标到最新

将以上 6 个指标更新至 2026-04 月份最新数据，并设置每月自动更新。

#### 5.2 新增以下高优先级指标

| 指标代码（建议） | 指标名称 | 频率 | 数据来源 | 用途 |
|----------------|---------|------|---------|------|
| LPR_1Y | 贷款市场报价利率（1年期） | 月度 | AKShare `macro_china_lpr` | 利率环境判断 |
| LPR_5Y | 贷款市场报价利率（5年期） | 月度 | AKShare `macro_china_lpr` | 房地产/长端利率 |
| SHIBOR_1W | 上海银行间同业拆放利率（1周） | 日度 | AKShare `macro_china_shibo_rate` | 短期资金松紧度 |
| SOCIAL_FINANCE | 社会融资规模（月度新增，亿元） | 月度 | AKShare `macro_china_shrzgm` | 信用扩张/收缩 |
| NEW_LOANS | 人民币贷款新增（月度，亿元） | 月度 | AKShare `macro_china_rmjj` | 信贷环境 |
| USD_CNY | 美元/人民币汇率（收盘价） | 日度 | AKShare `currency_convert` | 跨境资金流向 |
| US_10Y_YIELD | 美国10年期国债收益率（%） | 日度 | AKShare / 同花顺 | 外部流动性压力 |

#### 5.3 更新频率要求

| 频率类型 | 指标 | 更新时间 |
|---------|------|---------|
| 月度 | CPI/PPI/M2/PMI/LPR/社融/新增贷款 | 每月数据发布后24小时内 |
| 日度 | SHIBOR/USD_CNY/US_10Y | 每个交易日 18:00 前 |

---

## 六、需求五：events 表事件类型扩充（P1 优先级）

### 背景

`events` 表目前有 96,207 条记录，但**全部是龙虎榜（event_type='龙虎榜'）**，表结构已支持多种事件类型，但数据从未被补充过。

### 现有字段（已足够，无需新增）

```
code, event_date, event_type, title, content, 
sentiment, impact_strength, expected_duration, source
```

### 需求明细

请补充以下事件类型的历史数据：

| event_type | 中文说明 | 历史回填范围 | 更新频率 | 数据来源 |
|------------|---------|------------|---------|---------|
| `earnings_beat` | 业绩超预期 | 2020-01-01 至今 | 财报季（每季度） | AKShare `stock_yjyg_em`（业绩预告） |
| `earnings_miss` | 业绩不及预期 | 2020-01-01 至今 | 财报季 | 同上 |
| `insider_buy` | 董监高增持 | 2020-01-01 至今 | 每周 | 来自 insider_trades 表同步 |
| `insider_sell` | 董监高大额减持（>100万元） | 2020-01-01 至今 | 每周 | 来自 insider_trades 表同步 |
| `buyback` | 公司回购 | 2022-01-01 至今 | 每日 | AKShare `stock_repurchase_em` |
| `lock_up_expire` | 限售股解禁 | 2022-01-01 至今 | 每月 | AKShare `stock_restricted_release_summary_em` |

### content 字段格式要求

为方便系统解析，`content` 字段请统一使用如下格式：

```
earnings_beat:  "超预期幅度: +35.2%, 实际EPS: 1.23元, 预期EPS: 0.91元"
insider_buy:    "增持金额: 1200万元, 增持比例: 0.5%, 增持人: 王总"
buyback:        "回购金额: 5000万元, 回购价格上限: 45.00元"
lock_up_expire: "解禁数量: 1.2亿股, 解禁比例: 8.5%, 解禁类型: 定增股份"
```

---

## 七、需求六：新增 sector_sentiment 每日板块情绪表（P1 优先级）

### 背景

TrendRadar 的 `ai_analysis_results.sector_impacts_json` 每日产生板块情绪评分，但当前存储在 `finance_public_opinion` 数据库中，格式为 JSON 文本，不便于量化系统直接查询。

### 新建表：`sector_sentiment_daily`（在 finance 库）

```sql
CREATE TABLE sector_sentiment_daily (
    trade_date      DATE NOT NULL,
    sector          VARCHAR(50) NOT NULL,      -- 申万一级行业名称
    sentiment       NUMERIC(4,2) NOT NULL,     -- -1(极负) 到 +1(极正)
    confidence      NUMERIC(4,2),              -- 0.0 到 1.0
    reasoning       TEXT,                       -- AI 推理摘要
    source          VARCHAR(20) DEFAULT 'trendradar',
    created_at      TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (trade_date, sector)
);
```

### 数据同步要求

- **来源**：从 `finance_public_opinion.ai_analysis_results.sector_impacts_json` 解析，每日同步一次
- **时间**：每个交易日 21:30（TrendRadar 分析完成后）
- **历史数据**：回填 finance_public_opinion 中现有的 33 条历史记录（2026-03-22 起）
- **申万映射**：利用已有的 `sector_stock_mapping` 表，将 TrendRadar 板块名映射到申万一级行业

---

## 八、需求七：stock_info 行业分类完善（P2 优先级）

### 背景

`stock_info.industry` 字段目前为申万一级行业，但量化系统需要**申万二级行业**来做更精细的行业中性化和持仓集中度控制。

### 需求明细

| 项目 | 内容 |
|------|------|
| 新增字段 | `sw_l2_industry VARCHAR(50)`（申万二级行业） |
| 新增字段 | `sw_l3_industry VARCHAR(50)`（申万三级行业，选填） |
| 覆盖 | 所有活跃股票（约 5,000 只） |
| 更新频率 | 每月更新一次（申万行业分类调整不频繁） |
| 数据来源 | AKShare `stock_board_industry_name_em` |

---

## 九、优先级汇总

| 优先级 | 需求 | 预估工作量 | 交付物 |
|--------|------|----------|--------|
| **P0** | money_flow 字段补全（north_net_buy/融资融券） | 3-5 天 | 历史3年 + 日更新脚本 |
| **P0** | trade_constraints 历史回填（2020-今） | 2-3 天 | 历史数据 + 日更新脚本 |
| **P1** | macro_data 更新 + 新增7个指标 | 2-3 天 | 历史数据 + 月/日更新脚本 |
| **P1** | insider_trades 历史扩充（2020-今）+ 周更新 | 2 天 | 历史数据 + 周更新脚本 |
| **P1** | events 表新增5类事件（2020-今） | 3-4 天 | 历史数据 + 定期更新脚本 |
| **P1** | 新建 sector_sentiment_daily + TrendRadar 同步 | 1-2 天 | 表结构 + 同步脚本 |
| **P2** | stock_info 补充申万二级行业 | 1 天 | 字段更新 |

---

*文档生成：2026-04-12 | 需求方：量化交易系统组 | 数据来源：数据库现状探查*
