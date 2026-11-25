"""Tests for crm_ingestion.src_to_pre: dedupe and upsert."""

import json

from crm_ingestion.models import CrmRecord
from crm_ingestion.src_to_pre import dedupe, run, upsert
from crm_ingestion.store import layer_path, write_records
from conftest import sample_raw


def _records(*raws):
    return [CrmRecord.from_raw(raw) for raw in raws]


def test_dedupe_keeps_latest():
    out = dedupe(_records(
        sample_raw("1", "2026-11-01T10:00:00Z", amount=100),
        sample_raw("1", "2026-11-01T10:00:00Z", amount=100),  # re-fetch
        sample_raw("1", "2026-11-02T10:00:00Z", amount=200),  # update
        sample_raw("2", "2026-11-01T10:00:00Z", amount=50),
    ))
    assert len(out) == 2
    assert [r for r in out if r.record_id == "1"][0].amount == 200


def test_dedupe_is_idempotent_on_replay():
    batch = _records(
        sample_raw("1", "2026-11-02T10:00:00Z", amount=200),
        sample_raw("2", "2026-11-01T10:00:00Z", amount=50),
    )
    merged, created, updated = upsert(batch, batch)
    assert created == 0 and updated == 0
    assert len(merged) == 2


def test_upsert_counts_created_and_updated():
    existing = _records(sample_raw("1", "2026-11-01T10:00:00Z", amount=100))
    batch = _records(
        sample_raw("1", "2026-11-02T10:00:00Z", amount=200),  # update
        sample_raw("2", "2026-11-01T10:00:00Z", amount=50),   # create
        sample_raw("1", "2026-10-01T10:00:00Z", amount=1),    # stale, ignored
    )
    merged, created, updated = upsert(existing, dedupe(batch))
    assert (created, updated) == (1, 1)
    assert [r for r in merged if r.record_id == "1"][0].amount == 200


def test_run_merges_into_existing_pre(settings):
    write_records(
        layer_path(settings.pre_dir, "Account"),
        _records(sample_raw("1", "2026-11-01T10:00:00Z", amount=100)),
    )
    raw_path = layer_path(settings.raw_dir, "Account")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps([
        sample_raw("1", "2026-11-02T10:00:00Z", amount=200),
        sample_raw("2", "2026-11-01T10:00:00Z", amount=50),
        {"Id": "bad"},  # quarantined, never reaches PRE
    ]))
    result = run(settings, "Account")
    assert result.src_in == 3
    assert result.quarantined == 1
    assert (result.created, result.updated) == (1, 1)
    assert result.pre_after == 2
    pre = json.loads(layer_path(settings.pre_dir, "Account").read_text())
    assert {row["Id"] for row in pre} == {"1", "2"}
    quarantine = list(settings.quarantine_dir.glob("*.jsonl"))
    assert len(quarantine) == 1


def test_run_first_load_creates_pre(settings):
    raw_path = layer_path(settings.raw_dir, "Account")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps([sample_raw("1"), sample_raw("2")]))
    result = run(settings, "Account")
    assert result.pre_before == 0
    assert result.pre_after == 2
