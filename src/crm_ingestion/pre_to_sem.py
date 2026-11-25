"""PRE to SEM: promote to the current-state layer, applying deletes.

SEM reflects the current state: records flagged ``is_deleted`` are
excluded here. PRE is untouched, so full history (including deleted
records) is preserved there. PRE to SEM is a fast filter because both
layers hold the same shape; in production both are Iceberg tables.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from .config import Settings
from .logging_config import get_logger, setup_logging
from .models import CrmRecord
from .store import layer_path, read_validated_records, write_records

logger = get_logger("pre_to_sem")


@dataclass
class PromotionResult:
    """Row counts for one PRE -> SEM run."""

    object_name: str
    pre_in: int
    sem_out: int
    deletes_applied: int


def apply_deletes(records: list[CrmRecord]) -> tuple[list[CrmRecord], int]:
    """Split records into active rows and the count of deleted ones."""
    active = [record for record in records if not record.is_deleted]
    return active, len(records) - len(active)


def run(settings: Settings, object_name: str) -> PromotionResult:
    """Run PRE -> SEM for one object. Returns row counts."""
    pre_path = layer_path(settings.pre_dir, object_name)
    sem_path = layer_path(settings.sem_dir, object_name)
    pre_records = read_validated_records(pre_path)
    active, deletes = apply_deletes(pre_records)
    write_records(sem_path, active)
    logger.info(
        "pre_to_sem done object=%s pre_in=%d sem_out=%d deletes_applied=%d",
        object_name,
        len(pre_records),
        len(active),
        deletes,
    )
    return PromotionResult(
        object_name=object_name,
        pre_in=len(pre_records),
        sem_out=len(active),
        deletes_applied=deletes,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote PRE to SEM, applying deletes.")
    parser.add_argument("--object", default="Account", help="object, e.g. Account")
    parser.add_argument("--config", default=None, help="path to config.yaml")
    args = parser.parse_args()
    settings = Settings.load(args.config)
    setup_logging(settings.log_level)
    run(settings, args.object)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
