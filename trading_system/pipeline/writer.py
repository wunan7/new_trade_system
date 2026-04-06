"""Write factor computation results to factor_cache table."""
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import insert as pg_insert
from loguru import logger


def write_factor_cache(session, model_class, records: list[dict],
                       batch_size: int = 500) -> int:
    """Bulk upsert records into factor_cache table.

    Uses PostgreSQL ON CONFLICT DO UPDATE for idempotent writes.

    Args:
        session: SQLAlchemy session
        model_class: FactorCache ORM model class
        records: list of dicts with factor values
        batch_size: number of records per INSERT batch

    Returns:
        Total number of rows affected
    """
    if not records:
        return 0

    conflict_keys = ["trade_date", "stock_code"]
    mapper = inspect(model_class)
    all_columns = [c.key for c in mapper.columns]
    update_columns = [c for c in all_columns if c not in conflict_keys]

    total = 0
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]

        stmt = pg_insert(model_class.__table__).values(batch)
        update_dict = {c: stmt.excluded[c] for c in update_columns if c in batch[0]}

        if update_dict:
            stmt = stmt.on_conflict_do_update(
                index_elements=conflict_keys,
                set_=update_dict,
            )
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=conflict_keys)

        result = session.execute(stmt)
        total += result.rowcount

    logger.info(f"Wrote {total} rows to factor_cache ({len(records)} records in {(len(records)-1)//batch_size+1} batches)")
    return total
