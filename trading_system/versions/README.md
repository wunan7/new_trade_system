# 策略版本归档

每个版本目录保存该版本的核心策略代码快照，用于复现回测结果。

## 版本列表

| 版本 | 日期 | 总收益 | 年化 | 夏普 | 胜率 | 盈亏比 | 核心改动 |
|------|------|:------:|:----:|:----:|:----:|:------:|---------|
| V1 | 2026-04-05 | -19.86% | -7.40% | -1.36 | 34.15% | 0.86 | 基础版，估值数据缺失 |
| V2 | 2026-04-06 | +12.63% | +4.22% | 0.21 | 42.53% | 1.33 | 补全估值/资金面历史数据 |
| V3 | 2026-04-09 | +24.41% | +7.88% | 0.55 | 42.82% | 1.46 | 修复事件驱动单位错误+舆情T-1 |
| V5c | 2026-04-11 | +22.50% | +7.30% | 0.51 | 44.92% | 1.60 | +IC/IR confidence调整，新增10个因子 |
| **V6** | **2026-04-13** | **+25.95%** | **+8.34%** | **0.68** | **47.45%** | **1.70** | **涨跌停约束+5类事件驱动+IC调整（联合效果）** |
| V6-pure | 2026-04-14 | +24.60% | +7.93% | 0.61 | 46.86% | 1.63 | 纯Phase3c，无IC调整（当前生产代码）★ |
| V6-con | 2026-04-13 | +23.09% | +7.48% | 0.64 | 47.60% | 1.67 | V6基础+情绪/宏观市场状态维度（保守变体，回撤最低10.14%） |

注：V1-V3 回测不含涨跌停约束（结果偏乐观）。V6 起含涨跌停/停牌真实约束，结果更接近实盘。
V4a/b/c 为参数调优实验，V5a/b 为因子过滤实验，均不优于基线，未单独归档。

## 各版本关键文件

### V3（当前生产/最优总收益版本）
```
v3/
├── value.py          # 价值策略（原始）
├── growth.py         # 成长策略（原始）
├── momentum.py       # 动量策略（原始）
├── event_driven.py   # 事件驱动（已修复单位）
├── generator.py      # 信号生成器（无IC调整）
├── engine.py         # 回测引擎（33因子，无IC调整）
├── stop_loss.py      # 止损参数（含event fallback到multi）
├── position_sizer.py # 仓位管理
├── constraints.py    # 硬性约束
├── base.py           # 策略权重表
├── market_state.py   # 市场状态检测
└── sentiment.py      # 舆情因子（T-1修复）
```

### V5c（最优质量版本：胜率+盈亏比更高）
```
v5c/
├── value.py          # 同V3
├── growth.py         # 同V3
├── momentum.py       # 同V3
├── event_driven.py   # 同V3
├── generator.py      # 新增 IC_WEIGHTS + _adjust_confidence_by_ic()
├── engine.py         # 新增IC调整 + 43因子SQL
├── stop_loss.py      # 同V3
├── position_sizer.py # 同V3
├── constraints.py    # 同V3
├── base.py           # 同V3
├── market_state.py   # 同V3
└── sentiment.py      # 同V3
```

## 如何切换版本

版本文件仅用于参考和复现，不直接执行。如需切换到某版本运行回测：

```bash
# 备份当前
cp trading_system/signals/generator.py trading_system/signals/generator.py.bak

# 切换到V3
cp trading_system/versions/v3/generator.py trading_system/signals/generator.py
cp trading_system/versions/v3/engine.py trading_system/backtest/engine.py

# 运行回测
python run_backtest.py
```

## 下一版本规划

**V6** 方向：
- 改进因子在策略评分中的使用方式（将 IC/IR 纳入策略内部评分权重，而非只调整 confidence）
- 解决 IC confidence 调整导致交易数减少（-19%）的问题
- 探索市场状态自适应的 IC 权重（牛市/熊市下因子有效性不同）
