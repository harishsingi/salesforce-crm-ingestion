"""Shared JSON layer I/O: read/write record lists, one file per object.

Local layers are JSON files (``<object>.json``) so the pipeline runs
without Spark or Glue. In production these are Parquet in S3 / Iceberg
tables; the stage code only depends on the record lists, not the format.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import CrmIngestionError
from .models import CrmRecord


def layer_path(directory: Path, object_name: str) -> Path:
    """File for one object in one layer, e.g. ``data/pre/account.json``."""
    return Path(directory) / f"{object_name.lower()}.json"


def read_records(path: Path) -> list[dict[str, Any]]:
    """Read a JSON list file; missing file means an empty layer (first run)."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CrmIngestionError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, list):
        raise CrmIngestionError(f"{path} must hold a JSON list of records")
    return data


def read_validated_records(path: Path) -> list[CrmRecord]:
    """Read a layer file and validate every record (corrupt state fails loudly)."""
    from .validate import validate_records

    result = validate_records(read_records(path))
    if result.rejected:
        reasons = "; ".join(item.reason for item in result.rejected[:3])
        raise CrmIngestionError(
            f"{path} holds {len(result.rejected)} invalid record(s): {reasons}"
        )
    return result.valid


def write_records(path: Path, records: list[CrmRecord]) -> None:
    """Write records, overwriting the file (a re-run is safe and clean)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps([r.to_dict() for r in records], indent=2)
    path.write_text(payload + "\n", encoding="utf-8")
