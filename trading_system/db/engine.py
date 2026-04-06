"""Reuse finance_data's engine, provide trading_system session_scope"""
from contextlib import contextmanager
from finance_data.db.engine import engine, SessionLocal


def get_engine():
    return engine


@contextmanager
def session_scope():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
