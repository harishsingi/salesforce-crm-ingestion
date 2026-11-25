"""Tests for crm_ingestion.models: validation and normalisation."""

import pytest

from crm_ingestion.errors import SchemaValidationError
from crm_ingestion.models import CrmRecord, format_timestamp, parse_timestamp
from conftest import sample_raw


def test_valid_record_parses():
    record = CrmRecord.from_raw(sample_raw())
    assert record.record_id == "0010001"
    assert record.name == "Account 1"
    assert record.is_deleted is False
    assert record.amount == 1000
    assert record.last_modified.year == 2026


def test_is_deleted_accepts_string_and_bool():
    assert CrmRecord.from_raw(sample_raw(is_deleted="true")).is_deleted is True
    assert CrmRecord.from_raw(sample_raw(is_deleted=True)).is_deleted is True
    assert CrmRecord.from_raw(sample_raw(is_deleted=False)).is_deleted is False


def test_missing_id_rejected():
    raw = sample_raw()
    del raw["Id"]
    with pytest.raises(SchemaValidationError, match="Id"):
        CrmRecord.from_raw(raw)


def test_missing_timestamp_rejected():
    raw = sample_raw()
    del raw["LastModifiedDate"]
    with pytest.raises(SchemaValidationError, match="LastModifiedDate"):
        CrmRecord.from_raw(raw)


def test_bad_timestamp_rejected():
    with pytest.raises(SchemaValidationError):
        CrmRecord.from_raw(sample_raw(ts="yesterday"))
    with pytest.raises(SchemaValidationError):
        CrmRecord.from_raw(sample_raw(ts="2026-13-01T10:00:00Z"))


def test_non_object_rejected():
    with pytest.raises(SchemaValidationError):
        CrmRecord.from_raw(["not", "a", "dict"])


def test_negative_amount_rejected():
    with pytest.raises(SchemaValidationError, match="Amount"):
        CrmRecord.from_raw(sample_raw(amount=-5))


def test_bool_amount_rejected():
    with pytest.raises(SchemaValidationError, match="Amount"):
        CrmRecord.from_raw(sample_raw(amount=True))


def test_bad_is_deleted_rejected():
    with pytest.raises(SchemaValidationError, match="IsDeleted"):
        CrmRecord.from_raw(sample_raw(is_deleted="yes"))


def test_extra_fields_preserved():
    record = CrmRecord.from_raw({**sample_raw(), "Industry": "Manufacturing"})
    assert record.extra == {"Industry": "Manufacturing"}
    assert record.to_dict()["Industry"] == "Manufacturing"


def test_round_trip_through_dict():
    record = CrmRecord.from_raw(sample_raw(is_deleted="true"))
    again = CrmRecord.from_raw(record.to_dict())
    assert again == record


def test_parse_timestamp_handles_offsets():
    parsed = parse_timestamp("2026-11-10T12:00:00+02:00")
    assert format_timestamp(parsed) == "2026-11-10T10:00:00Z"
