"""Shared fixtures: an isolated Settings pointing at tmp dirs."""

from __future__ import annotations

import pytest

from crm_ingestion.config import Settings


@pytest.fixture
def settings(tmp_path):
    """Settings with every layer directory under tmp_path."""
    return Settings(
        raw_dir=tmp_path / "raw",
        pre_dir=tmp_path / "pre",
        sem_dir=tmp_path / "sem",
        quarantine_dir=tmp_path / "quarantine",
        synthetic_dir=tmp_path / "synthetic",
        overlap_minutes=15,
        dq_max_age_hours=36,
    )


def sample_raw(
    record_id="0010001",
    ts="2026-11-10T10:00:00Z",
    name="Account 1",
    is_deleted="false",
    amount=1000,
):
    """One API-shaped record dict."""
    return {
        "Id": record_id,
        "Name": name,
        "LastModifiedDate": ts,
        "IsDeleted": is_deleted,
        "Amount": amount,
    }
