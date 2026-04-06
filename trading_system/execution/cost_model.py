"""Trading cost model for A-share market simulation."""


# Fee rates
COMMISSION_RATE = 0.00025     # 万2.5 bilateral
COMMISSION_MIN = 5.0          # minimum 5 yuan per trade
STAMP_TAX_RATE = 0.001        # 千1, sell only
SLIPPAGE_RATE = 0.0002        # 万2 market impact


def calc_trade_cost(price: float, shares: int, direction: str) -> dict:
    """Calculate trading costs for a single trade.

    Args:
        price: execution price per share (yuan)
        shares: number of shares traded
        direction: "BUY" or "SELL"

    Returns:
        dict with commission, stamp_tax, slippage, total (all in yuan)
    """
    amount = price * shares

    commission = max(amount * COMMISSION_RATE, COMMISSION_MIN)
    stamp_tax = amount * STAMP_TAX_RATE if direction == "SELL" else 0.0
    slippage = amount * SLIPPAGE_RATE

    return {
        "commission": round(commission, 2),
        "stamp_tax": round(stamp_tax, 2),
        "slippage": round(slippage, 2),
        "total": round(commission + stamp_tax + slippage, 2),
    }
