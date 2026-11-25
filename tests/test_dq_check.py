"""Tests for crm_ingestion.dq_check: freshness alerting."""

from datetime import datetime, timedelta, timezone

import pytest

from crm_ingestion.dq_check import check, run
from crm_ingestion.errors import DqAlertError
from crm_ingestion.models import CrmRecord
from crm_ingestion.store import layer_path, write_records
from conftest import sample_raw

NOW = datetime(2026, 11, 25, 12, 0, 0, tzinfo=timezone.utc)  # noon check
MAX_AGE = timedelta(hours=36)


def _records(*raws):
    return [CrmRecord.from_raw(raw) for raw in raws]


def test_fresh_data_ok():
    result = check(
        _records(sample_raw("1", "2026-11-25T10:00:00Z")),
        "Account", MAX_AGE, now=NOW,
    )
    assert result.status == "ok"
    assert result.age == timedelta(hours=2)


def test_stale_data_flagged():
    result = check(
        _records(sample_raw("1", "2026-11-20T10:00:00Z")),
        "Account", MAX_AGE, now=NOW,
    )
    assert result.status == "stale"


def test_empty_target_flagged():
    result = check([], "Account", MAX_AGE, now=NOW)
    assert result.status == "empty"
    assert result.latest is None


def test_run_ok_on_fresh_sem(settings):
    write_records(
        layer_path(settings.sem_dir, "Account"),
        _records(sample_raw("1", "2026-11-25T10:00:00Z")),
    )
    result = run(settings, "Account", now=NOW)
    assert result.status == "ok"


def test_run_raises_on_stale_sem(settings):
    write_records(
        layer_path(settings.sem_dir, "Account"),
        _records(sample_raw("1", "2026-11-20T10:00:00Z")),
    )
    with pytest.raises(DqAlertError, match="no new data"):
        run(settings, "Account", now=NOW)


def test_run_raises_on_empty_sem(settings):
    with pytest.raises(DqAlertError, match="no data"):
        run(settings, "Account", now=NOW)
