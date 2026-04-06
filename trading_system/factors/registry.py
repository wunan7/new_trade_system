from dataclasses import dataclass
from enum import Enum


class FactorCategory(str, Enum):
    TECHNICAL = "technical"
    FUNDAMENTAL = "fundamental"
    MONEY_FLOW = "money_flow"      # placeholder for future
    SENTIMENT = "sentiment"        # placeholder for future


@dataclass
class FactorDef:
    name: str
    category: FactorCategory
    description: str
    data_sources: list[str]
    nullable: bool = False


FACTOR_REGISTRY: dict[str, FactorDef] = {}


def register_factor(name: str, category: FactorCategory, description: str,
                    data_sources: list[str], nullable: bool = False) -> None:
    FACTOR_REGISTRY[name] = FactorDef(name, category, description, data_sources, nullable)


def get_factors_by_category(category: str | FactorCategory) -> list[FactorDef]:
    if isinstance(category, str):
        category = FactorCategory(category)
    return [f for f in FACTOR_REGISTRY.values() if f.category == category]


def get_all_factor_names() -> list[str]:
    return sorted(FACTOR_REGISTRY.keys())


# Register all 26 factors:
# Technical (13)
register_factor("momentum_5d", FactorCategory.TECHNICAL, "5-day return", ["stock_daily"])
register_factor("momentum_20d", FactorCategory.TECHNICAL, "20-day return", ["stock_daily"])
register_factor("momentum_60d", FactorCategory.TECHNICAL, "60-day return", ["stock_daily"])
register_factor("volatility_20d", FactorCategory.TECHNICAL, "20-day annualized volatility", ["stock_daily"])
register_factor("volatility_60d", FactorCategory.TECHNICAL, "60-day annualized volatility", ["stock_daily"])
register_factor("atr_14d", FactorCategory.TECHNICAL, "14-day Average True Range", ["stock_daily"])
register_factor("volume_ratio_5d", FactorCategory.TECHNICAL, "Volume / 5-day avg volume", ["stock_daily"])
register_factor("turnover_dev", FactorCategory.TECHNICAL, "Turnover deviation from 20-day mean", ["stock_daily"])
register_factor("macd_signal", FactorCategory.TECHNICAL, "MACD DIF value", ["stock_daily"])
register_factor("adx", FactorCategory.TECHNICAL, "14-day ADX trend strength", ["stock_daily"])
register_factor("bb_width", FactorCategory.TECHNICAL, "Bollinger Band width", ["stock_daily"])
register_factor("rs_vs_index", FactorCategory.TECHNICAL, "Relative strength vs CSI300", ["stock_daily", "index_daily"])
register_factor("obv_slope", FactorCategory.TECHNICAL, "OBV 20-day regression slope", ["stock_daily"])

# Fundamental (13)
register_factor("roe", FactorCategory.FUNDAMENTAL, "ROE from financial_summary", ["financial_summary"])
register_factor("gross_margin", FactorCategory.FUNDAMENTAL, "Gross margin from financial_summary", ["financial_summary"])
register_factor("net_margin", FactorCategory.FUNDAMENTAL, "Net margin from financial_summary", ["financial_summary"])
register_factor("debt_ratio", FactorCategory.FUNDAMENTAL, "Debt-to-assets from financial_summary", ["financial_summary"])
register_factor("revenue_growth", FactorCategory.FUNDAMENTAL, "Revenue YoY growth from financial_summary", ["financial_summary"])
register_factor("profit_growth", FactorCategory.FUNDAMENTAL, "Net profit YoY growth from financial_summary", ["financial_summary"])
register_factor("ocf_to_profit", FactorCategory.FUNDAMENTAL, "Operating cashflow / net profit", ["financial_cashflow", "financial_income"])
register_factor("accrual_ratio", FactorCategory.FUNDAMENTAL, "(NP - OCF) / total assets", ["financial_income", "financial_cashflow", "financial_balance"])
register_factor("goodwill_ratio", FactorCategory.FUNDAMENTAL, "Goodwill / equity", ["financial_balance"])
register_factor("pe_ttm", FactorCategory.FUNDAMENTAL, "PE TTM from stock_valuation", ["stock_valuation"], nullable=True)
register_factor("pb", FactorCategory.FUNDAMENTAL, "PB from stock_valuation", ["stock_valuation"], nullable=True)
register_factor("ps_ttm", FactorCategory.FUNDAMENTAL, "PS TTM from stock_valuation", ["stock_valuation"], nullable=True)
register_factor("dividend_yield", FactorCategory.FUNDAMENTAL, "Dividend yield from dividends + valuation", ["stock_dividend", "stock_valuation"], nullable=True)

# Money flow (4)
register_factor("north_flow_chg", FactorCategory.MONEY_FLOW, "北向资金流入强度(5日均值/流通市值)", ["money_flow", "stock_valuation"])
register_factor("north_days", FactorCategory.MONEY_FLOW, "近20日北向净买入正值天数占比", ["money_flow"])
register_factor("main_net_ratio", FactorCategory.MONEY_FLOW, "主力净流入占成交额比", ["money_flow", "stock_daily"])
register_factor("margin_chg_rate", FactorCategory.MONEY_FLOW, "5日融资余额变化率", ["money_flow"])

# Sentiment (3)
register_factor("sentiment_score", FactorCategory.SENTIMENT, "Composite sentiment from TrendRadar", [], nullable=True)
register_factor("news_heat", FactorCategory.SENTIMENT, "News heat score from TrendRadar", [], nullable=True)
register_factor("news_mention_count", FactorCategory.SENTIMENT, "Number of news mentions in past 24h", [], nullable=True)
