"""CRM record model: validation and normalisation for one object row.

The API / on-disk shape keeps Salesforce field names (``Id``,
``LastModifiedDate``, ``IsDeleted``, ...). This module is the single place
that knows how to turn that shape into a typed record and back, so no
other stage parses timestamps or booleans by hand.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .errors import SchemaValidationError

# ISO 8601 with an explicit zone, e.g. 2026-11-22T10:00:00Z.
_TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)

#: Fields every record must carry. Everything else is optional.
REQUIRED_FIELDS = ("Id", "LastModifiedDate")


def parse_timestamp(value: Any) -> datetime:
    """Parse an ISO 8601 timestamp into an aware UTC datetime.

    Raises:
        SchemaValidationError: if the value is not a string or not ISO 8601.
    """
    if not isinstance(value, str) or not _TIMESTAMP_RE.match(value):
        raise SchemaValidationError(
            f"LastModifiedDate must be an ISO 8601 timestamp, got {value!r}",
            field="LastModifiedDate",
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:  # e.g. month 13, hour 25
        raise SchemaValidationError(
            f"LastModifiedDate is not a valid timestamp: {value!r}",
            field="LastModifiedDate",
        ) from exc
    return parsed.astimezone(timezone.utc)


def format_timestamp(moment: datetime) -> str:
    """Format an aware datetime as Salesforce-style ISO 8601 (``...Z``)."""
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_is_deleted(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in ("true", "false"):
        return value.lower() == "true"
    raise SchemaValidationError(
        f"IsDeleted must be a boolean or 'true'/'false', got {value!r}",
        field="IsDeleted",
    )


@dataclass(frozen=True)
class CrmRecord:
    """One validated CRM object row (an Account in the local demo)."""

    record_id: str
    last_modified: datetime
    name: str | None = None
    is_deleted: bool = False
    amount: int | None = None
    # Any extra API fields, kept verbatim so nothing is silently dropped.
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "CrmRecord":
        """Validate a raw API dict and build a record.

        Raises:
            SchemaValidationError: on a missing/invalid required field.
        """
        if not isinstance(raw, dict):
            raise SchemaValidationError(
                f"record must be an object, got {type(raw).__name__}",
                field=None,
            )
        for required in REQUIRED_FIELDS:
            if required not in raw:
                raise SchemaValidationError(
                    f"missing required field: {required}", field=required
                )
        record_id = raw["Id"]
        if not isinstance(record_id, str) or not record_id.strip():
            raise SchemaValidationError("Id must be a non-empty string", field="Id")
        name = raw.get("Name")
        if name is not None and not isinstance(name, str):
            raise SchemaValidationError("Name must be a string", field="Name")
        amount = raw.get("Amount")
        if amount is not None:
            if isinstance(amount, bool) or not isinstance(amount, int):
                raise SchemaValidationError("Amount must be an integer", field="Amount")
            if amount < 0:
                raise SchemaValidationError("Amount must not be negative", field="Amount")
        known = {"Id", "Name", "LastModifiedDate", "IsDeleted", "Amount"}
        return cls(
            record_id=record_id,
            last_modified=parse_timestamp(raw["LastModifiedDate"]),
            name=name,
            is_deleted=_parse_is_deleted(raw.get("IsDeleted", False)),
            amount=amount,
            extra={k: v for k, v in raw.items() if k not in known},
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialise back to the Salesforce-shaped dict (for JSON layers)."""
        out: dict[str, Any] = {
            "Id": self.record_id,
            "Name": self.name,
            "LastModifiedDate": format_timestamp(self.last_modified),
            "IsDeleted": "true" if self.is_deleted else "false",
            "Amount": self.amount,
        }
        out.update(self.extra)
        return out
