"""Schema validation and quarantine of bad records.

This is the SRC schema check: every incoming record is validated before
it reaches PRE. Valid records continue; invalid ones are quarantined to
JSONL with the reason attached, counted, and logged, never silently
dropped and never allowed to poison the clean layers.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .errors import SchemaValidationError
from .models import CrmRecord

logger = logging.getLogger(__name__)


@dataclass
class RejectedRecord:
    """One record that failed validation, with the reason it was rejected."""

    raw: Any
    reason: str


@dataclass
class ValidationResult:
    """Outcome of validating a batch."""

    valid: list[CrmRecord] = field(default_factory=list)
    rejected: list[RejectedRecord] = field(default_factory=list)

    @property
    def rows_in(self) -> int:
        return len(self.valid) + len(self.rejected)


def validate_records(raw_records: Iterable[Any]) -> ValidationResult:
    """Validate a batch; valid records and quarantined rejects are separated."""
    result = ValidationResult()
    for raw in raw_records:
        try:
            result.valid.append(CrmRecord.from_raw(raw))
        except SchemaValidationError as exc:
            result.rejected.append(RejectedRecord(raw=raw, reason=str(exc)))
    if result.rejected:
        logger.warning(
            "schema validation rejected=%d rows_in=%d",
            len(result.rejected),
            result.rows_in,
        )
    return result


def write_quarantine(rejected: list[RejectedRecord], path: Path) -> Path | None:
    """Write rejected records as JSONL (``{"reason": ..., "record": ...}``).

    Returns the path written, or ``None`` when there is nothing to quarantine.
    """
    if not rejected:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps({"reason": item.reason, "record": item.raw}, default=str)
        for item in rejected
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.warning("quarantined rejected=%d path=%s", len(rejected), path)
    return path
