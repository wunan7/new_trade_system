from sqlalchemy import Column, Date, DateTime, VARCHAR, NUMERIC, Integer, Boolean, Index, PrimaryKeyConstraint, JSON
from sqlalchemy.dialects.postgresql import JSONB
from trading_system.db.base import Base, TimestampMixin, _now_cn

# Use JSONB on PostgreSQL (better indexing/operators); fall back to JSON on SQLite for tests.
_JSONB = JSONB().with_variant(JSON(), "sqlite")


class FactorCache(Base, TimestampMixin):
    __tablename__ = "factor_cache"
    __table_args__ = (
        PrimaryKeyConstraint("trade_date", "stock_code"),
        Index("idx_factor_cache_code", "stock_code"),
    )
    trade_date = Column(Date, nullable=False)
    stock_code = Column(VARCHAR(10), nullable=False)
    # Technical factors (13)
    momentum_5d = Column(NUMERIC(20, 6))
    momentum_20d = Column(NUMERIC(20, 6))
    momentum_60d = Column(NUMERIC(20, 6))
    volatility_20d = Column(NUMERIC(20, 6))
    volatility_60d = Column(NUMERIC(20, 6))
    atr_14d = Column(NUMERIC(20, 6))
    volume_ratio_5d = Column(NUMERIC(20, 6))
    turnover_dev = Column(NUMERIC(20, 6))
    macd_signal = Column(NUMERIC(20, 6))
    adx = Column(NUMERIC(20, 6))
    bb_width = Column(NUMERIC(20, 6))
    rs_vs_index = Column(NUMERIC(20, 6))
    obv_slope = Column(NUMERIC(20, 6))
    # New technical factors (4)
    amplitude_20d = Column(NUMERIC(20, 6))
    upper_shadow_ratio = Column(NUMERIC(20, 6))
    ma_alignment = Column(NUMERIC(20, 6))
    volume_price_corr = Column(NUMERIC(20, 6))
    # Fundamental factors (13)
    roe = Column(NUMERIC(20, 6))
    gross_margin = Column(NUMERIC(20, 6))
    net_margin = Column(NUMERIC(20, 6))
    debt_ratio = Column(NUMERIC(20, 6))
    revenue_growth = Column(NUMERIC(20, 6))
    profit_growth = Column(NUMERIC(20, 6))
    ocf_to_profit = Column(NUMERIC(20, 6))
    accrual_ratio = Column(NUMERIC(20, 6))
    goodwill_ratio = Column(NUMERIC(20, 6))
    pe_ttm = Column(NUMERIC(20, 6))
    pb = Column(NUMERIC(20, 6))
    ps_ttm = Column(NUMERIC(20, 6))
    dividend_yield = Column(NUMERIC(20, 6))
    # New fundamental factors (4)
    roa = Column(NUMERIC(20, 6))
    current_ratio = Column(NUMERIC(20, 6))
    peg = Column(NUMERIC(20, 6))
    market_cap_pct = Column(NUMERIC(20, 6))
    # Money flow factors (4)
    north_flow_chg = Column(NUMERIC(20, 6))
    north_days = Column(NUMERIC(20, 6))
    main_net_ratio = Column(NUMERIC(20, 6))
    margin_chg_rate = Column(NUMERIC(20, 6))
    # New money flow factors (2)
    big_order_net_ratio = Column(NUMERIC(20, 6))
    consecutive_main_inflow = Column(NUMERIC(20, 6))
    # Sentiment factors (3)
    sentiment_score = Column(NUMERIC(20, 6))
    news_heat = Column(NUMERIC(20, 6))
    news_mention_count = Column(NUMERIC(20, 6))
    # Full factors JSON
    factors_json = Column(_JSONB)


class SignalHistory(Base, TimestampMixin):
    __tablename__ = "signal_history"
    __table_args__ = (
        Index("idx_signal_history_stock_date", "stock_code", "trade_date"),
        Index("idx_signal_history_strategy_date", "strategy", "trade_date"),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(Date, nullable=False)
    stock_code = Column(VARCHAR(10), nullable=False)
    strategy = Column(VARCHAR(20), nullable=False)
    direction = Column(NUMERIC(4, 2))       # -1.0 to 1.0
    confidence = Column(NUMERIC(4, 2))      # 0.0 to 1.0
    holding_period = Column(Integer)
    entry_price = Column(NUMERIC(12, 4))
    stop_loss = Column(NUMERIC(12, 4))
    take_profit = Column(NUMERIC(12, 4))
    factors_json = Column(_JSONB)
    was_executed = Column(Boolean, default=False)
    filter_reason = Column(VARCHAR(100))
    llm_override = Column(VARCHAR(100))
    created_at = Column(DateTime, default=_now_cn)


class PortfolioPosition(Base, TimestampMixin):
    __tablename__ = "portfolio_positions"
    __table_args__ = (
        Index("idx_pos_status", "status", "code"),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(VARCHAR(10), nullable=False)
    open_date = Column(Date, nullable=False)
    open_price = Column(NUMERIC(12, 4), nullable=False)
    current_price = Column(NUMERIC(12, 4))
    position_pct = Column(NUMERIC(6, 4))
    shares = Column(Integer, nullable=False)
    strategy_source = Column(VARCHAR(20), nullable=False)
    signal_id = Column(Integer)
    stop_loss_price = Column(NUMERIC(12, 4))
    take_profit_price = Column(NUMERIC(12, 4))
    max_hold_days = Column(Integer)
    status = Column(VARCHAR(10), default="open")         # open / closed
    close_date = Column(Date)
    close_price = Column(NUMERIC(12, 4))
    close_reason = Column(VARCHAR(50))                   # stop_loss / take_profit / trailing_stop / time_limit / signal
    pnl_pct = Column(NUMERIC(8, 4))


class TradeLog(Base, TimestampMixin):
    __tablename__ = "trade_log"
    __table_args__ = (
        Index("idx_trade_date", "trade_date", "code"),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(Date, nullable=False)
    code = Column(VARCHAR(10), nullable=False)
    direction = Column(VARCHAR(4), nullable=False)       # BUY / SELL
    price = Column(NUMERIC(12, 4), nullable=False)
    shares = Column(Integer, nullable=False)
    amount = Column(NUMERIC(16, 2))
    strategy = Column(VARCHAR(20))
    signal_id = Column(Integer)
    position_id = Column(Integer)
    commission = Column(NUMERIC(10, 2))
    stamp_tax = Column(NUMERIC(10, 2))
    slippage = Column(NUMERIC(10, 2))
    is_paper = Column(Boolean, default=True)


class PortfolioNav(Base, TimestampMixin):
    __tablename__ = "portfolio_nav"
    nav_date = Column(Date, primary_key=True)
    total_value = Column(NUMERIC(16, 2))
    cash = Column(NUMERIC(16, 2))
    positions_value = Column(NUMERIC(16, 2))
    position_count = Column(Integer)
    daily_return = Column(NUMERIC(8, 6))
    cumulative_return = Column(NUMERIC(10, 6))
    benchmark_return = Column(NUMERIC(8, 6))
    excess_return = Column(NUMERIC(8, 6))
    drawdown = Column(NUMERIC(8, 6))
    max_drawdown = Column(NUMERIC(8, 6))
    sharpe_30d = Column(NUMERIC(8, 4))
    is_paper = Column(Boolean, default=True)
