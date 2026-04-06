"""Portfolio drawdown monitoring and alert levels."""
from enum import Enum


class DrawdownLevel(str, Enum):
    NORMAL = "normal"                # < 8%
    YELLOW = "yellow"                # >= 8%, no new positions
    ORANGE = "orange"                # >= 12%, reduce to <= 50%
    RED = "red"                      # >= 16%, reduce to <= 20%
    CIRCUIT_BREAK = "circuit_break"  # >= 18%, full liquidation


# Drawdown thresholds and forced position limits
_LEVELS = [
    (0.25, DrawdownLevel.CIRCUIT_BREAK, 0.0),
    (0.20, DrawdownLevel.RED, 0.20),
    (0.15, DrawdownLevel.ORANGE, 0.50),
    (0.12, DrawdownLevel.YELLOW, 0.8),   # 0.8 means max 80% position
]


class DrawdownMonitor:
    """Track portfolio high-water mark and current drawdown."""

    def __init__(self, initial_capital: float = 1_000_000):
        self.high_water_mark = initial_capital
        self.level = DrawdownLevel.NORMAL
        self.current_drawdown = 0.0

    def update(self, total_value: float) -> DrawdownLevel:
        """Update with latest portfolio value, return alert level."""
        if total_value > self.high_water_mark:
            self.high_water_mark = total_value

        if self.high_water_mark > 0:
            self.current_drawdown = (self.high_water_mark - total_value) / self.high_water_mark
        else:
            self.current_drawdown = 0.0

        for threshold, level, _ in _LEVELS:
            if self.current_drawdown >= threshold:
                self.level = level
                return level

        self.level = DrawdownLevel.NORMAL
        return DrawdownLevel.NORMAL

    def get_position_limit_override(self) -> float | None:
        """Return forced max position ratio, or None if normal.
        """
        if self.level == DrawdownLevel.CIRCUIT_BREAK:
            return 0.0
        if self.level == DrawdownLevel.RED:
            return 0.20
        if self.level == DrawdownLevel.ORANGE:
            return 0.50
        if self.level == DrawdownLevel.YELLOW:
            return 0.80
        return None

    def allows_new_positions(self) -> bool:
        """Whether new positions can be opened."""
        return self.level != DrawdownLevel.CIRCUIT_BREAK
