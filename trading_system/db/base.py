"""trading_system own Base + TimestampMixin"""
from datetime import datetime, timezone, timedelta
from sqlalchemy import Column, DateTime
from sqlalchemy.orm import declarative_base

_TZ_CN = timezone(timedelta(hours=8))
Base = declarative_base()


def _now_cn():
    return datetime.now(_TZ_CN).replace(tzinfo=None)


class TimestampMixin:
    updated_at = Column(DateTime, default=_now_cn, onupdate=_now_cn)
