"""Stop-loss and take-profit calculation by strategy type."""
from datetime import date
from dataclasses import dataclass


# Strategy-specific parameters: (fixed_stop_loss%, tp_trigger%, trailing_pct%, max_hold_days)
STRATEGY_PARAMS = {
    "momentum": {"stop_pct": 0.05, "tp_trigger": 0.10, "trailing_pct": 0.05, "max_days": 10},
    "growth":   {"stop_pct": 0.08, "tp_trigger": 0.15, "trailing_pct": 0.04, "max_days": 60},
    "value":    {"stop_pct": 0.12, "tp_trigger": 0.20, "trailing_pct": 0.04, "max_days": 60},
    "multi":    {"stop_pct": 0.08, "tp_trigger": 0.15, "trailing_pct": 0.04, "max_days": 60},
}

# Progressive trailing-stop tightening
TRAILING_TIERS = [
    (0.40, 0.03),   # profit > 40% → 3% trailing
    (0.20, 0.04),   # profit > 20% → 4% trailing
    (0.10, 0.05),   # profit > 10% → 5% trailing
]


class StopLossCalculator:

    def calc_initial(self, strategy: str, entry_price: float,
                     atr: float = None) -> tuple[float, float]:
        """Calculate initial stop-loss and take-profit prices.

        Returns (stop_loss_price, take_profit_price).
        """
        params = STRATEGY_PARAMS.get(strategy, STRATEGY_PARAMS["multi"])

        fixed_stop = entry_price * (1 - params["stop_pct"])

        # ATR-based stop: tighter of fixed vs ATR
        if atr and atr > 0:
            atr_stop = entry_price - atr * 2.0
            stop_loss = max(fixed_stop, atr_stop)  # pick tighter (higher) stop
        else:
            stop_loss = fixed_stop

        take_profit = entry_price * (1 + params["tp_trigger"])

        return round(stop_loss, 4), round(take_profit, 4)

    def check_exit(self, strategy: str, entry_price: float, open_date: date,
                   current_price: float, max_price: float,
                   current_date: date, stop_loss_price: float) -> tuple[bool, str]:
        """Check if a position should be exited.

        Args:
            strategy: strategy name
            entry_price: original buy price
            open_date: position open date
            current_price: today's close price
            max_price: highest price since entry (for trailing stop)
            current_date: today's date
            stop_loss_price: initial stop-loss price

        Returns:
            (should_exit, reason) where reason is one of:
            'stop_loss', 'trailing_stop', 'time_limit', or '' if no exit
        """
        params = STRATEGY_PARAMS.get(strategy, STRATEGY_PARAMS["multi"])

        # 1. Fixed stop-loss
        if current_price <= stop_loss_price:
            return True, "stop_loss"

        # 2. Trailing stop (progressive tightening)
        if max_price > entry_price:
            unrealized_pct = (max_price - entry_price) / entry_price
            trailing_pct = None
            for threshold, pct in TRAILING_TIERS:
                if unrealized_pct >= threshold:
                    trailing_pct = pct
                    break
            if trailing_pct is None and unrealized_pct >= params["tp_trigger"]:
                trailing_pct = params["trailing_pct"]

            if trailing_pct is not None:
                trailing_stop = max_price * (1 - trailing_pct)
                if current_price <= trailing_stop:
                    return True, "trailing_stop"

        # 3. Time-based exit
        days_held = (current_date - open_date).days
        if days_held >= params["max_days"]:
            return True, "time_limit"

        return False, ""
