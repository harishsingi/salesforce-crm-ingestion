"""SRC to PRE: schema-checked upserts, deduped on record Id.

The raw batch is validated (schema check) and quarantined where invalid,
then merged into PRE: one row per Id, keeping the latest timestamp. A
straight re-fetch (same Id, same timestamp) and an update (same Id, newer
timestamp) both collapse to a single row, so overlaps and replays are
idempotent and the pipeline self-heals after an outage. PRE keeps full
history: an Id is never removed here, only superseded.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from .config import Settings
from .logging_config import get_logger, setup_logging
from .models import CrmRecord
from .store import layer_path, read_validated_records, write_records
from .validate import validate_records, write_quarantine

logger = get_logger("src_to_pre")


@dataclass
class UpsertResult:
    """Row counts for one SRC -> PRE run."""

    object_name: str
    src_in: int
    quarantined: int
    pre_before: int
    created: int
    updated: int
    pre_after: int


def dedupe(records: list[CrmRecord]) -> list[CrmRecord]:
    """One row per Id, keeping the latest timestamp; sorted by Id.

    A tie on timestamp keeps the later record in the batch (a re-fetch
    carries identical values, so either copy is correct).
    """
    best: dict[str, CrmRecord] = {}
    for record in records:
        current = best.get(record.record_id)
        if current is None or record.last_modified >= current.last_modified:
            best[record.record_id] = record
    return [best[key] for key in sorted(best)]


def upsert(
    existing: list[CrmRecord], batch: list[CrmRecord]
) -> tuple[list[CrmRecord], int, int]:
    """Merge a deduped batch into existing PRE state.

    Returns ``(merged, created, updated)``: an Id is *created* when it was
    absent, *updated* when the batch carries a newer timestamp for it, and
    left alone when the batch is older or identical (a replayed fetch).
    """
    merged = {record.record_id: record for record in existing}
    created = updated = 0
    for record in batch:
        current = merged.get(record.record_id)
        if current is None:
            merged[record.record_id] = record
            created += 1
        elif record.last_modified > current.last_modified:
            merged[record.record_id] = record
            updated += 1
    return [merged[key] for key in sorted(merged)], created, updated


def run(settings: Settings, object_name: str) -> UpsertResult:
    """Run SRC -> PRE for one object. Returns row counts."""
    from .store import read_records

    src_path = layer_path(settings.raw_dir, object_name)
    pre_path = layer_path(settings.pre_dir, object_name)

    validated = validate_records(read_records(src_path))
    if validated.rejected:
        write_quarantine(
            validated.rejected,
            layer_path(settings.quarantine_dir, object_name).with_suffix(".jsonl"),
        )
    batch = dedupe(validated.valid)
    existing = read_validated_records(pre_path)
    merged, created, updated = upsert(existing, batch)
    write_records(pre_path, merged)
    logger.info(
        "src_to_pre done object=%s src_in=%d quarantined=%d pre_before=%d "
        "created=%d updated=%d pre_after=%d",
        object_name,
        len(validated.valid) + len(validated.rejected),
        len(validated.rejected),
        len(existing),
        created,
        updated,
        len(merged),
    )
    return UpsertResult(
        object_name=object_name,
        src_in=len(validated.valid) + len(validated.rejected),
        quarantined=len(validated.rejected),
        pre_before=len(existing),
        created=created,
        updated=updated,
        pre_after=len(merged),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote SRC (raw) to PRE (upserts).")
    parser.add_argument("--object", default="Account", help="object, e.g. Account")
    parser.add_argument("--config", default=None, help="path to config.yaml")
    args = parser.parse_args()
    settings = Settings.load(args.config)
    setup_logging(settings.log_level)
    run(settings, args.object)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
