"""Tests for crm_ingestion.download and generate_data, plus the full pipeline."""

import json
from datetime import date

from crm_ingestion import download, generate_data, pipeline
from crm_ingestion.api_client import SyntheticApiClient
from crm_ingestion.store import layer_path
from conftest import sample_raw


def test_generate_is_deterministic():
    first = generate_data.generate(base_date=date(2026, 11, 25))
    second = generate_data.generate(base_date=date(2026, 11, 25))
    assert first == second


def test_generate_has_duplicate_and_update():
    rows = generate_data.generate(base_date=date(2026, 11, 25))
    assert len(rows) == 102  # 100 accounts + duplicate + update
    assert rows[100] == rows[0]  # exact re-fetch duplicate
    assert rows[101]["Id"] == rows[1]["Id"]
    assert rows[101]["LastModifiedDate"] == "2026-11-25T00:00:00Z"
    assert rows[101]["Amount"] == 91000


def test_generate_dates_relative_to_base():
    rows = generate_data.generate(base_date=date(2026, 11, 25))
    dates = {row["LastModifiedDate"][:10] for row in rows}
    assert max(dates) == "2026-11-25"
    assert min(dates) == "2026-10-29"  # 28-day window


def test_download_full_load_when_no_watermark(settings, tmp_path):
    synth = settings.synthetic_dir
    synth.mkdir(parents=True)
    (synth / "account.json").write_text(json.dumps([
        sample_raw("1", "2026-11-01T10:00:00Z"),
        sample_raw("2", "2026-11-02T10:00:00Z"),
    ]))
    result = download.run(settings, "Account")
    assert result.watermark is None
    assert result.rows_fetched == 2
    assert result.rows_rejected == 0
    raw = json.loads(layer_path(settings.raw_dir, "Account").read_text())
    assert len(raw) == 2


def test_download_uses_watermark_with_overlap(settings):
    # PRE already holds data up to Nov 10; only newer rows should be fetched.
    from crm_ingestion.models import CrmRecord
    from crm_ingestion.store import write_records

    write_records(
        layer_path(settings.pre_dir, "Account"),
        [CrmRecord.from_raw(sample_raw("0", "2026-11-10T10:00:00Z"))],
    )
    synth = settings.synthetic_dir
    synth.mkdir(parents=True)
    (synth / "account.json").write_text(json.dumps([
        sample_raw("1", "2026-11-01T10:00:00Z"),  # older than watermark: skipped
        sample_raw("2", "2026-11-10T09:50:00Z"),  # inside the 15-min overlap: kept
        sample_raw("3", "2026-11-11T10:00:00Z"),  # newer: kept
    ]))
    result = download.run(settings, "Account")
    assert result.watermark == "2026-11-10T10:00:00Z"
    assert result.rows_fetched == 2
    raw = json.loads(layer_path(settings.raw_dir, "Account").read_text())
    assert {row["Id"] for row in raw} == {"2", "3"}


def test_download_quarantines_bad_rows(settings):
    synth = settings.synthetic_dir
    synth.mkdir(parents=True)
    (synth / "account.json").write_text(json.dumps([
        sample_raw("1"),
        {"Id": "2"},  # invalid: quarantined
    ]))
    result = download.run(settings, "Account")
    assert result.rows_fetched == 2
    assert result.rows_valid == 1
    assert result.rows_rejected == 1
    assert list(settings.quarantine_dir.glob("*.jsonl"))


def test_full_pipeline_end_to_end(settings, tmp_path):
    summary = pipeline.run(settings, ["Account"])
    account = summary["Account"]
    assert account["downloaded"] == 102  # 102 generated rows, all valid
    assert account["rejected"] == 0
    assert account["pre_rows"] == 100  # deduped to 100 unique Ids
    assert account["sem_rows"] == 100
    assert account["deletes_applied"] == 0
    assert account["dq_status"] == "ok"
    # A second run is a no-op replay: same counts, no duplicates.
    summary2 = pipeline.run(settings, ["Account"])
    assert summary2["Account"]["pre_rows"] == 100
    assert summary2["Account"]["sem_rows"] == 100
