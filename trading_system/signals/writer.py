"""Write signals to signal_history table."""
from dataclasses import asdict
from loguru import logger


def write_signals(session, signals: list, batch_size: int = 500) -> int:
    """Bulk insert signals into signal_history table.

    Args:
        session: SQLAlchemy session
        signals: list of Signal dataclass instances
        batch_size: number of records per INSERT batch

    Returns:
        Total number of rows inserted
    """
    if not signals:
        return 0

    from trading_system.db.models import SignalHistory

    # Convert Signal dataclasses to dicts, mapping 'factors' -> 'factors_json'
    records = []
    for sig in signals:
        record = asdict(sig)
        record["factors_json"] = record.pop("factors")
        records.append(record)

    # Batch insert (no upsert — signals are append-only)
    total = 0
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]

        # Use bulk_insert_mappings for performance
        session.bulk_insert_mappings(SignalHistory, batch)
        total += len(batch)

    logger.info(
        f"Wrote {total} signals to signal_history "
        f"({len(records)} records in {(len(records) - 1) // batch_size + 1} batches)"
    )
    return total
