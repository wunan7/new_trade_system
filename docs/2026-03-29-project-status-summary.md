# A股智能交易系统 - 阶段性总结报告

**日期：** 2026-03-29
**项目位置：** `C:\Users\wunan\projects\new_solution\`
**当前进度：** 第3层完成（共6层架构）

---

## 一、已完成工作

### 1.1 第1层：数据采集与存储 ✅

**状态：** 完成（由 `finance_data` 包提供）

**数据库表：**
- `stock_daily` (665万行) — 日线行情数据
- `stock_info` — 股票基本信息
- `financial_summary` — 财务摘要（5011只股票）
- `income_statement`, `balance_sheet`, `cashflow_statement` — 三大财务报表
- `stock_valuation` — 估值数据（2026-03-10后有数据）
- `dividends` — 分红数据
- `index_daily` — 指数数据（上证、深证、沪深300、创业板）

**数据源：**
- AKShare — 行情、财务、估值
- TrendRadar — 舆情数据（待集成）

---

### 1.2 第2层：因子计算引擎 ✅

**状态：** 完成（26个核心因子）

**模块结构：**
```
trading_system/
├── db/
│   ├── base.py          # SQLAlchemy Base + TimestampMixin
│   ├── models.py        # FactorCache, SignalHistory
│   └── engine.py        # DB连接管理
├── factors/
│   ├── registry.py      # 因子注册表（26个因子）
│   ├── technical.py     # 13个技术因子
│   ├── fundamental.py   # 13个基本面因子
│   └── utils.py         # 工具函数
├── pipeline/
│   ├── data_loader.py   # 数据加载器
│   ├── standardizer.py  # MAD去极值 + z-score标准化
│   ├── writer.py        # 批量写入
│   └── orchestrator.py  # 主协调器
└── scripts/
    └── calc_factors.py  # CLI工具
```

**已实现因子（26/80）：**

| 类别 | 因子 | 数量 |
|------|------|------|
| **技术因子** | momentum_5d/20d/60d, volatility_20d/60d, atr_14d, volume_ratio_5d, turnover_dev, macd_signal, adx, bb_width, rs_vs_index, obv_slope | 13 |
| **基本面因子** | roe, gross_margin, net_margin, debt_ratio, revenue_growth, profit_growth, ocf_to_profit, accrual_ratio, goodwill_ratio, pe_ttm, pb, ps_ttm, dividend_yield | 13 |

**测试覆盖：** 69个测试，全部通过

**使用示例：**
```bash
# 计算最新交易日因子
python scripts/calc_factors.py

# 指定日期
python scripts/calc_factors.py --date 2026-03-27

# 日期范围
python scripts/calc_factors.py --start 2026-03-01 --end 2026-03-27
```

---

### 1.3 第3层：多策略信号层 ✅

**状态：** 完成（3个策略 + 市场状态检测）

**模块结构：**
```
trading_system/
├── strategies/
│   ├── base.py          # BaseStrategy, Signal, MarketState, STRATEGY_WEIGHTS
│   ├── market_state.py  # 市场状态检测器（6状态）
│   ├── value.py         # 价值策略
│   ├── growth.py        # 成长策略
│   └── momentum.py      # 动量策略
├── signals/
│   ├── generator.py     # 信号生成器（主协调器）
│   └── writer.py        # 信号写入
└── scripts/
    └── gen_signals.py   # CLI工具
```

**市场状态检测（6状态）：**
- **趋势：** BULL（牛市）/ NEUTRAL（震荡）/ BEAR（熊市）
- **波动：** LOW（低波动）/ HIGH（高波动）
- **组合：** BULL_LOW, BULL_HIGH, NEUTRAL_LOW, NEUTRAL_HIGH, BEAR_LOW, BEAR_HIGH

**策略权重表：**
```
状态          | 价值 | 成长 | 动量 | 仓位上限
BULL_LOW      | 0.20 | 0.35 | 0.25 | 0.90
BULL_HIGH     | 0.10 | 0.25 | 0.35 | 0.80
NEUTRAL_LOW   | 0.30 | 0.15 | 0.10 | 0.60
NEUTRAL_HIGH  | 0.25 | 0.10 | 0.10 | 0.50
BEAR_LOW      | 0.40 | 0.05 | 0.05 | 0.40
BEAR_HIGH     | 0.30 | 0.00 | 0.00 | 0.20
```

**策略详情：**

1. **价值策略（ValueStrategy）**
   - 筛选：pb<30%分位, roe>12, 股息率>2%, 负债率<60%
   - 评分：0.30*(1-pb分位) + 0.30*roe/50 + 0.20*股息率/0.10 + 0.20*经营现金流/利润/3
   - 输出：Top 20，持有期60天

2. **成长策略（GrowthStrategy）**
   - 筛选：利润增速>30%, 营收增速>20%, roe>8%
   - 评分：0.40*利润增速/200 + 0.30*营收增速/100 + 0.20*roe/50 + 0.10*毛利率/80
   - 输出：Top 20，持有期60天

3. **动量策略（MomentumStrategy）**
   - 筛选：20日动量>80%分位, 60日动量>70%分位, 未过热(<50%), 成交量比>0.5
   - 评分：0.35*20日动量分位 + 0.25*60日动量分位 + 0.20*量比 + 0.20*ADX/60
   - 输出：Top 15，持有期10天

**信号聚合逻辑：**
- 同一股票出现在多个策略 → 按市场状态权重加权平均
- 方向、置信度加权平均，持有期取最大值
- 策略标记为 "multi"

**测试覆盖：** 33个测试，全部通过

**E2E验证结果（2026-03-27）：**
```
市场状态：BEAR_HIGH（熊市+高波动）
策略权重：value=0.3, growth=0.0, momentum=0.0
生成信号：18个价值策略信号

样本信号：
  002191: value, direction=1.00, confidence=0.70
  600997: value, direction=0.82, confidence=0.70
  002022: value, direction=0.80, confidence=0.60
```

**使用示例：**
```bash
# 生成最新交易日信号
python scripts/gen_signals.py

# 指定日期
python scripts/gen_signals.py --date 2026-03-27

# 指定股票
python scripts/gen_signals.py --date 2026-03-27 --codes 600519,000858
```

---

## 二、遗留工作

### 2.1 第2层因子扩展（54个因子待补充）

**资金面因子（~10个）** — 依赖 `money_flow` 表
- 主力净流入、大单占比、北向资金流向、融资融券余额变化等
- **阻塞原因：** `money_flow` 表尚未采集

**舆情因子（~8个）** — 依赖 `stock_sentiment_daily` 聚合表
- 新闻情绪得分、社交媒体热度、分析师评级变化等
- **阻塞原因：** TrendRadar 舆情数据未聚合到日度表

**另类因子（~7个）** — 依赖特殊数据源
- 拥挤度、期权PCR、融券余额、股东减持等
- **阻塞原因：** 数据源未接入

**剩余技术因子（~12个）**
- 涨跌停频率、振幅、上下影线比、缺口统计等
- **阻塞原因：** 需要 `trade_constraints` 表（涨跌停限制数据）

**剩余基本面因子（~17个）**
- 更细的盈利质量指标、成长持续性、现金流质量等
- **可选增强：** 可基于现有财务报表计算

**因子评价体系（可选）**
- IC/IC_IR、分组单调性、因子衰减分析
- 月度因子有效性评估

---

### 2.2 第3层策略扩展

**事件驱动策略** — 依赖 `events` 表
- 财报发布、股东大会、重大公告等事件触发
- **阻塞原因：** 事件表未建立

**技术择时策略** — 依赖更多技术指标
- 突破策略、均线交叉、形态识别等
- **阻塞原因：** 需要更多技术因子

**行业轮动策略** — 依赖行业分类和行业指数
- 行业景气度、行业相对强弱
- **阻塞原因：** 行业数据未整理

**中性化处理（可选）**
- 市值中性、行业中性（回归取残差）
- 提升因子纯净度

---

## 三、未开始工作

### 3.1 第4层：风控与仓位管理

**核心功能：**
- 止损/止盈计算（基于ATR、支撑位等）
- 仓位管理（凯利公式、风险平价）
- 回撤控制（最大回撤限制、动态减仓）
- 相关性控制（避免同质化持仓）

**输入：** `signal_history` 表
**输出：** `position_target` 表（目标仓位）

---

### 3.2 第5层：执行与订单管理

**核心功能：**
- 订单生成（市价单、限价单）
- 滑点控制
- 成交跟踪
- 实盘对接（模拟盘/实盘API）

**输入：** `position_target` 表
**输出：** `orders` 表, `trades` 表

---

### 3.3 第6层：监控与评估

**核心功能：**
- 实时持仓监控
- 绩效归因分析
- 风险指标监控（夏普比率、最大回撤、胜率等）
- 策略评估报告

**输入：** `trades`, `positions`, `signal_history`
**输出：** 可视化报表、告警通知

---

### 3.4 回测引擎

**核心功能：**
- 历史信号回测
- 策略参数优化
- 蒙特卡洛模拟
- 压力测试

**依赖：** 完整的历史因子数据 + 信号数据

---

## 四、技术债务与优化方向

### 4.1 性能优化

- **因子计算并行化：** 当前单线程，可用 multiprocessing 加速
- **数据库索引优化：** 为高频查询字段添加复合索引
- **缓存机制：** Redis 缓存热点因子数据

### 4.2 代码质量

- **类型注解完善：** 部分函数缺少类型提示
- **日志规范化：** 统一日志格式和级别
- **配置管理：** 将硬编码参数移至配置文件

### 4.3 测试覆盖

- **集成测试：** 端到端流程测试（因子→信号→持仓）
- **性能测试：** 大规模数据下的性能基准
- **边界测试：** 极端市场条件下的鲁棒性

---

## 五、数据依赖清单

### 5.1 已有数据

| 表名 | 数据量 | 时间范围 | 更新频率 |
|------|--------|----------|----------|
| stock_daily | 665万行 | 历史至今 | 每日 |
| financial_summary | 5011股 | 最新季报 | 季度 |
| stock_valuation | 稀疏 | 2026-03-10后 | 每日 |
| index_daily | 4指数 | 历史至今 | 每日 |

### 5.2 缺失数据

| 数据类型 | 用途 | 优先级 | 预计工作量 |
|----------|------|--------|------------|
| money_flow | 资金面因子 | 高 | 2-3天 |
| stock_sentiment_daily | 舆情因子 | 中 | 需TrendRadar聚合 |
| trade_constraints | 涨跌停数据 | 中 | 1-2天 |
| events | 事件驱动策略 | 低 | 3-5天 |
| industry_classification | 行业轮动 | 低 | 1天 |

---

## 六、里程碑与时间线

### 已完成里程碑

- ✅ **M1（2026-03-26）：** 第2层因子引擎完成（26因子）
- ✅ **M2（2026-03-29）：** 第3层信号生成完成（3策略）

### 下一步里程碑

- **M3（预计1周）：** 第4层风控模块
  - 止损/止盈计算
  - 仓位管理
  - 回撤控制

- **M4（预计2周）：** 第5层执行模块
  - 订单生成
  - 模拟盘对接
  - 成交跟踪

- **M5（预计1周）：** 第6层监控评估
  - 实时监控
  - 绩效分析
  - 可视化报表

- **M6（预计2周）：** 回测引擎
  - 历史回测
  - 参数优化
  - 策略评估

---

## 七、当前系统能力

### 7.1 可用功能

1. **每日因子计算** — 5011只股票，26个因子，耗时约1分钟
2. **市场状态检测** — 实时判断6种市场状态
3. **信号生成** — 根据市场状态动态调整策略权重
4. **信号存储** — 所有信号记录到 `signal_history` 表

### 7.2 使用流程

```bash
# 步骤1：计算因子
python scripts/calc_factors.py --date 2026-03-27

# 步骤2：生成信号
python scripts/gen_signals.py --date 2026-03-27

# 步骤3：查询信号
psql -d finance -c "SELECT * FROM signal_history WHERE trade_date='2026-03-27' LIMIT 10"
```

### 7.3 系统限制

- **无实盘执行能力** — 信号生成后需人工决策
- **无风控约束** — 未考虑止损、仓位限制
- **无回测验证** — 策略有效性未经历史验证
- **因子覆盖不全** — 仅26/80因子，缺少资金面/舆情

---

## 八、项目文件结构

```
C:\Users\wunan\projects\new_solution\
├── trading_system/              # 主包
│   ├── db/                      # 数据库层（2个模型）
│   ├── factors/                 # 因子计算（26因子）
│   ├── pipeline/                # 数据流水线
│   ├── strategies/              # 策略模块（3策略）
│   ├── signals/                 # 信号生成
│   └── config.py                # 配置管理
├── scripts/                     # CLI工具
│   ├── calc_factors.py          # 因子计算
│   ├── gen_signals.py           # 信号生成
│   └── init_db.py               # 数据库初始化
├── tests/                       # 测试套件（102测试）
├── docs/                        # 文档
│   ├── 2026-03-26-a-stock-trading-system-design.md  # 系统设计
│   ├── 2026-03-29-layer3-strategy-plan.md           # 第3层实施计划
│   └── 2026-03-29-project-status-summary.md         # 本文档
└── pyproject.toml               # 项目配置
```

---

## 九、关键指标

| 指标 | 当前值 | 目标值 |
|------|--------|--------|
| 代码行数 | ~3500行 | ~10000行（完整系统） |
| 测试覆盖 | 102测试 | 200+测试 |
| 因子数量 | 26个 | 80个 |
| 策略数量 | 3个 | 8-10个 |
| 数据表 | 2个新表 | 6-8个新表 |
| 执行速度 | 1分钟/5011股 | <30秒（优化后） |

---

## 十、联系与协作

**项目负责人：** wunan
**技术栈：** Python 3.11, PostgreSQL, SQLAlchemy 2.0, pandas, numpy
**开发环境：** Windows 11, Git
**文档更新：** 2026-03-29

---

**下一步行动：**
1. 补充 `money_flow` 表数据采集
2. 开始第4层风控模块设计
3. 准备回测数据（历史因子 + 信号）
