from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from enum import Enum
import pandas as pd


class MarketState(str, Enum):
    BULL_LOW = "bull_low"
    BULL_HIGH = "bull_high"
    NEUTRAL_LOW = "neutral_low"
    NEUTRAL_HIGH = "neutral_high"
    BEAR_LOW = "bear_low"
    BEAR_HIGH = "bear_high"


@dataclass
class Signal:
    trade_date: date
    stock_code: str
    strategy: str
    direction: float          # 0.0 to 1.0 (v1: all bullish, no shorts)
    confidence: float         # 0.0 to 1.0
    holding_period: int       # days
    entry_price: float
    stop_loss: float
    take_profit: float
    factors: dict             # factor values used for this signal


# Market state → strategy allocation weights
STRATEGY_WEIGHTS: dict[MarketState, dict] = {
    MarketState.BULL_LOW: {
        "value": 0.15,
        "growth": 0.30,
        "momentum": 0.25,
        "event": 0.10,
        "position_limit": 0.90,
    },
    MarketState.BULL_HIGH: {
        "value": 0.10,
        "growth": 0.20,
        "momentum": 0.35,
        "event": 0.15,
        "position_limit": 0.80,
    },
    MarketState.NEUTRAL_LOW: {
        "value": 0.25,
        "growth": 0.15,
        "momentum": 0.10,
        "event": 0.10,
        "position_limit": 0.60,
    },
    MarketState.NEUTRAL_HIGH: {
        "value": 0.20,
        "growth": 0.10,
        "momentum": 0.10,
        "event": 0.10,
        "position_limit": 0.50,
    },
    MarketState.BEAR_LOW: {
        "value": 0.30,
        "growth": 0.05,
        "momentum": 0.05,
        "event": 0.10,
        "position_limit": 0.40,
    },
    MarketState.BEAR_HIGH: {
        "value": 0.25,
        "growth": 0.00,
        "momentum": 0.00,
        "event": 0.05,
        "position_limit": 0.20,
    },
}


class BaseStrategy(ABC):
    """Abstract base class for all stock-picking strategies."""

    @abstractmethod
    def generate(self, trade_date: date, factor_df: pd.DataFrame) -> list[Signal]:
        """Generate signals for the given date.

        Args:
            trade_date: The trading date
            factor_df: DataFrame with factors, indexed by stock_code

        Returns:
            List of Signal objects
        """
        pass
