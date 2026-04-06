from trading_system.db.base import Base
from trading_system.db.engine import engine, session_scope, get_engine


def init_db():
    """Create trading_system tables (idempotent)"""
    from trading_system.db import models  # noqa: ensure models registered
    e = get_engine()
    Base.metadata.create_all(bind=e)
