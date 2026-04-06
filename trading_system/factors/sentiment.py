"""Sentiment factors from TrendRadar (finance_public_opinion database)."""
import pandas as pd
from sqlalchemy import create_engine, text
from loguru import logger


_engine = None

def _get_sentiment_engine():
    """Get connection to finance_public_opinion database (cached)."""
    global _engine
    if _engine is None:
        _engine = create_engine('postgresql://postgres:postgres@localhost:5432/finance_public_opinion')
    return _engine


def _load_sentiment_data(trade_date) -> pd.DataFrame:
    """Load all sentiment columns from stock_sentiment_daily for a given date.

    Returns DataFrame indexed by stock_code with columns:
    sentiment_score, news_heat, news_mention_count.
    Returns empty DataFrame if no data.
    """
    engine = _get_sentiment_engine()
    sql = text("""
        SELECT stock_code, composite_sentiment, news_heat_score, news_mention_count
        FROM stock_sentiment_daily
        WHERE data_date = :date
    """)

    with engine.connect() as conn:
        result = conn.execute(sql, {"date": str(trade_date)})
        rows = result.fetchall()

    if not rows:
        logger.warning(f"No sentiment data for {trade_date}")
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=['stock_code', 'sentiment_score', 'news_heat', 'news_mention_count'])
    df.set_index('stock_code', inplace=True)
    return df


# Cache to avoid re-querying for same date across three factor functions
_cache_date = None
_cache_df = None


def _get_cached_sentiment(trade_date) -> pd.DataFrame:
    """Get sentiment data with single-date cache."""
    global _cache_date, _cache_df
    td_str = str(trade_date)
    if _cache_date != td_str:
        _cache_date = td_str
        _cache_df = _load_sentiment_data(trade_date)
    return _cache_df


def sentiment_score(df: pd.DataFrame, trade_date) -> pd.Series:
    """Composite sentiment score from TrendRadar AI analysis.

    Range: -1 (极度负面) to +1 (极度正面)
    """
    sent_df = _get_cached_sentiment(trade_date)
    if sent_df.empty or 'sentiment_score' not in sent_df.columns:
        return pd.Series(dtype=float)

    result = df.index.to_series().map(sent_df['sentiment_score'])
    # Only return if there are actual non-NaN values
    if result.notna().any():
        return result.astype(float)
    return pd.Series(dtype=float)


def news_heat(df: pd.DataFrame, trade_date) -> pd.Series:
    """News heat score: normalized mention frequency + relevance.

    Range: 0 (无新闻) to 10+ (热点股)
    """
    sent_df = _get_cached_sentiment(trade_date)
    if sent_df.empty or 'news_heat' not in sent_df.columns:
        return pd.Series(dtype=float)

    result = df.index.to_series().map(sent_df['news_heat'])
    if result.notna().any():
        return result.astype(float)
    return pd.Series(dtype=float)


def news_mention_count(df: pd.DataFrame, trade_date) -> pd.Series:
    """Number of news mentions in past 24h.

    Range: 0 to N
    """
    sent_df = _get_cached_sentiment(trade_date)
    if sent_df.empty or 'news_mention_count' not in sent_df.columns:
        return pd.Series(dtype=float)

    result = df.index.to_series().map(sent_df['news_mention_count'])
    if result.notna().any():
        return result.astype(float)
    return pd.Series(dtype=float)
