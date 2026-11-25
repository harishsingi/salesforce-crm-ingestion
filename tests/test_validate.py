"""Tests for crm_ingestion.validate: schema check + quarantine."""

import json

from crm_ingestion.validate import validate_records, write_quarantine
from conftest import sample_raw


def test_all_valid_passes():
    result = validate_records([sample_raw("1"), sample_raw("2")])
    assert len(result.valid) == 2
    assert result.rejected == []
    assert result.rows_in == 2


def test_invalid_records_separated_with_reasons():
    result = validate_records([
        sample_raw("1"),
        {"Id": "2"},  # missing LastModifiedDate
        sample_raw("3", ts="not-a-date"),
    ])
    assert len(result.valid) == 1
    assert len(result.rejected) == 2
    assert "LastModifiedDate" in result.rejected[0].reason
    assert result.rejected[0].raw["Id"] == "2"


def test_write_quarantine_jsonl(tmp_path):
    result = validate_records([{"Id": "2"}])
    path = tmp_path / "account.jsonl"
    written = write_quarantine(result.rejected, path)
    assert written == path
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["record"]["Id"] == "2"
    assert "LastModifiedDate" in entry["reason"]


def test_write_quarantine_empty_returns_none(tmp_path):
    assert write_quarantine([], tmp_path / "x.jsonl") is None
    assert not (tmp_path / "x.jsonl").exists()
