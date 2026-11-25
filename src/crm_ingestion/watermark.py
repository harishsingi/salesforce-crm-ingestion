"""Watermark logic: the delta is decided by the data, not the calendar.

For each table the watermark is the latest timestamp already in the
target, i.e. ``MAX(LastModifiedDate)``. In production that is an Athena
query over the target table; locally the target is a JSON file, so this
module reads the same maximum from it. The query built from the watermark
starts a small overlap before it, so a change landing exactly on the
boundary is not missed; idempotent upserts downstream make the overlap
safe to re-load.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

from .errors import WatermarkError
from .models import CrmRecord, format_timestamp

#: Overlap applied before the watermark so boundary changes are not missed.
DEFAULT_OVERLAP = timedelta(minutes=15)

#: Salesforce object names are simple identifiers; reject anything else so
#: a bad object name can never be interpolated into a query.
_OBJECT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

#: Columns fetched for every object in the local demo.
DEFAULT_FIELDS = ("Id", "Name", "LastModifiedDate", "IsDeleted", "Amount")


def max_timestamp(records: Iterable[CrmRecord]) -> datetime | None:
    """Latest ``last_modified`` across records, or ``None`` when empty."""
    latest: datetime | None = None
    for record in records:
        if latest is None or record.last_modified > latest:
            latest = record.last_modified
    return latest


def watermark_from_file(path: Path) -> datetime | None:
    """Read a target JSON file and return its MAX(LastModifiedDate).

    Returns ``None`` when the file does not exist yet (first load: no
    watermark, so the query is a full load). Raises :class:`WatermarkError`
    when the file exists but cannot be read or validated.
    """
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WatermarkError(f"cannot read target file {path}: {exc}") from exc
    if not isinstance(raw, list):
        raise WatermarkError(f"target file {path} must hold a JSON list")
    try:
        records = [CrmRecord.from_raw(item) for item in raw]
    except Exception as exc:  # SchemaValidationError, wrapped for the caller
        raise WatermarkError(f"target file {path} has invalid records: {exc}") from exc
    return max_timestamp(records)


def build_soql(
    object_name: str,
    watermark: datetime | None,
    overlap: timedelta = DEFAULT_OVERLAP,
    fields: Iterable[str] = DEFAULT_FIELDS,
) -> str:
    """Build the incremental query for one object.

    With a watermark, fetches only ``LastModifiedDate >= watermark - overlap``;
    without one, fetches everything (first load). Ordered by timestamp so a
    paged fetch resumes cleanly.
    """
    if not _OBJECT_RE.match(object_name):
        raise WatermarkError(f"invalid object name: {object_name!r}")
    field_list = ", ".join(fields)
    query = f"SELECT {field_list} FROM {object_name}"
    if watermark is not None:
        since = format_timestamp(watermark - overlap)
        query += f" WHERE LastModifiedDate >= {since}"
    return query + " ORDER BY LastModifiedDate ASC"
