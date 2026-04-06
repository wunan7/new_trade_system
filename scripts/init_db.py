"""Create factor_cache table in PostgreSQL"""
from trading_system.db import init_db

if __name__ == "__main__":
    init_db()
    print("factor_cache table created successfully")
