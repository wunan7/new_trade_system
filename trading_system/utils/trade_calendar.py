"""Trading calendar utility: check if a date is a trading day.

Uses AKShare (Sina source) to fetch the full A-share trading calendar,
with local caching to avoid repeated API calls.
"""
from datetime import date, datetime
from pathlib import Path
import json

from loguru import logger

_CACHE_FILE = Path(__file__).parent.parent / "data" / "trade_calendar.json"
_calendar_set: set[str] | None = None


def _load_calendar() -> set[str]:
    """Load trading calendar, using local cache or fetching from AKShare."""
    global _calendar_set
    if _calendar_set is not None:
        return _calendar_set

    # Try local cache first (refresh if older than 7 days)
    if _CACHE_FILE.exists():
        try:
            data = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
            cached_at = datetime.fromisoformat(data["cached_at"])
            if (datetime.now() - cached_at).days < 7:
                _calendar_set = set(data["dates"])
                logger.debug(f"Loaded {len(_calendar_set)} trade dates from cache")
                return _calendar_set
        except Exception:
            pass  # Cache corrupted, re-fetch

    # Fetch from AKShare
    try:
        import akshare as ak
        df = ak.tool_trade_date_hist_sina()
        dates = [d.strftime("%Y-%m-%d") for d in df["trade_date"]]
        _calendar_set = set(dates)

        # Save cache
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(
            json.dumps({"cached_at": datetime.now().isoformat(), "dates": dates},
                       ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info(f"Fetched {len(dates)} trade dates from AKShare, cached to {_CACHE_FILE}")
    except Exception as e:
        logger.warning(f"Failed to fetch trade calendar from AKShare: {e}, falling back to weekday check")
        _calendar_set = set()

    return _calendar_set


def is_trading_day(d: date | None = None) -> bool:
    """Check if the given date (default: today) is an A-share trading day."""
    if d is None:
        d = date.today()

    cal = _load_calendar()
    if cal:
        return d.strftime("%Y-%m-%d") in cal
    else:
        # Fallback: weekday only (no holiday awareness)
        return d.weekday() < 5


def get_latest_trading_day(d: date | None = None) -> date:
    """Get the most recent trading day on or before the given date."""
    if d is None:
        d = date.today()

    cal = _load_calendar()
    if cal:
        from datetime import timedelta
        for i in range(30):  # Look back up to 30 days
            check = d - timedelta(days=i)
            if check.strftime("%Y-%m-%d") in cal:
                return check

    # Fallback
    from datetime import timedelta
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d
