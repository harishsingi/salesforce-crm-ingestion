"""Tests for crm_ingestion.pre_to_sem: deletes applied, history kept."""

import json

from crm_ingestion.models import CrmRecord
from crm_ingestion.pre_to_sem import apply_deletes, run
from crm_ingestion.store import layer_path, write_records
from conftest import sample_raw


def _records(*raws):
    return [CrmRecord.from_raw(raw) for raw in raws]


def test_apply_deletes_excludes_deleted():
    active, deletes = apply_deletes(_records(
        sample_raw("1", is_deleted="false"),
        sample_raw("2", is_deleted="true"),
        sample_raw("3", is_deleted="true"),
    ))
    assert [r.record_id for r in active] == ["1"]
    assert deletes == 2


def test_run_keeps_pre_history_and_writes_active_sem(settings):
    write_records(
        layer_path(settings.pre_dir, "Account"),
        _records(
            sample_raw("1", is_deleted="false"),
            sample_raw("2", is_deleted="true"),
        ),
    )
    result = run(settings, "Account")
    assert result.pre_in == 2
    assert result.sem_out == 1
    assert result.deletes_applied == 1
    # PRE still holds the deleted record (history preserved).
    pre = json.loads(layer_path(settings.pre_dir, "Account").read_text())
    assert {row["Id"] for row in pre} == {"1", "2"}
    sem = json.loads(layer_path(settings.sem_dir, "Account").read_text())
    assert [row["Id"] for row in sem] == ["1"]


def test_run_with_no_deletes(settings):
    write_records(
        layer_path(settings.pre_dir, "Account"),
        _records(sample_raw("1")),
    )
    result = run(settings, "Account")
    assert result.sem_out == 1 and result.deletes_applied == 0
