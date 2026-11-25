"""Tests for crm_ingestion.watermark: MAX(timestamp) and SOQL building."""

import json
from datetime import datetime, timezone

import pytest

from crm_ingestion.errors import WatermarkError
from crm_ingestion.models import CrmRecord
from crm_ingestion.watermark import build_soql, max_timestamp, watermark_from_file
from conftest import sample_raw


def _dt(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def test_max_timestamp_picks_latest():
    records = [
        CrmRecord.from_raw(sample_raw("1", "2026-11-01T10:00:00Z")),
        CrmRecord.from_raw(sample_raw("2", "2026-11-05T10:00:00Z")),
        CrmRecord.from_raw(sample_raw("3", "2026-11-03T10:00:00Z")),
    ]
    assert max_timestamp(records) == _dt("2026-11-05T10:00:00Z")


def test_max_timestamp_empty_is_none():
    assert max_timestamp([]) is None


def test_watermark_from_missing_file_is_none(tmp_path):
    assert watermark_from_file(tmp_path / "nope.json") is None


def test_watermark_from_file_reads_max(tmp_path):
    path = tmp_path / "account.json"
    path.write_text(json.dumps([
        sample_raw("1", "2026-11-01T10:00:00Z"),
        sample_raw("2", "2026-11-07T10:00:00Z"),
    ]))
    assert watermark_from_file(path) == _dt("2026-11-07T10:00:00Z")


def test_watermark_from_corrupt_file_raises(tmp_path):
    path = tmp_path / "account.json"
    path.write_text("{not json")
    with pytest.raises(WatermarkError):
        watermark_from_file(path)


def test_soql_with_watermark_applies_overlap():
    soql = build_soql("Account", _dt("2026-11-10T10:00:00Z"))
    assert "FROM Account" in soql
    # 15-minute overlap before the watermark.
    assert "LastModifiedDate >= 2026-11-10T09:45:00Z" in soql
    assert "ORDER BY LastModifiedDate ASC" in soql


def test_soql_without_watermark_is_full_load():
    soql = build_soql("Account", None)
    assert "WHERE" not in soql
    assert "FROM Account" in soql


def test_soql_rejects_bad_object_name():
    with pytest.raises(WatermarkError):
        build_soql("Account; DROP TABLE x", _dt("2026-11-10T10:00:00Z"))
