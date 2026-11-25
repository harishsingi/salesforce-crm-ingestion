"""Tests for crm_ingestion.api_client: retries, backoff, paging, synthetic mode."""

import json
from datetime import datetime, timezone

import pytest

from crm_ingestion.api_client import SalesforceApiClient, SyntheticApiClient
from crm_ingestion.errors import ApiAuthError, ApiError
from conftest import sample_raw


def _ok(records, next_url=None):
    payload = {"records": records, "done": next_url is None}
    if next_url:
        payload["nextRecordsUrl"] = next_url
    return 200, json.dumps(payload).encode()


class FakeTransport:
    """Scripted (status, body) responses; records sleeps via the sleep fn."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def __call__(self, url, headers):
        self.calls += 1
        return self.responses.pop(0)


def _client(transport, **kwargs):
    sleeps = []
    client = SalesforceApiClient(
        "https://example.my.salesforce.com",
        "token",
        max_retries=kwargs.pop("max_retries", 3),
        backoff_base_seconds=0,
        request_fn=transport,
        sleep_fn=sleeps.append,
        **kwargs,
    )
    return client, sleeps


def test_success_first_try():
    transport = FakeTransport([_ok([sample_raw()])])
    client, sleeps = _client(transport)
    assert len(client.query("SELECT Id FROM Account")) == 1
    assert transport.calls == 1
    assert sleeps == []


def test_retries_on_500_then_succeeds():
    transport = FakeTransport([(500, b"boom"), _ok([sample_raw()])])
    client, sleeps = _client(transport)
    assert len(client.query("SELECT Id FROM Account")) == 1
    assert transport.calls == 2
    assert len(sleeps) == 1  # one backoff delay before the retry


def test_retries_on_429_then_succeeds():
    transport = FakeTransport([(429, b"slow down"), _ok([sample_raw()])])
    client, sleeps = _client(transport)
    assert len(client.query("SELECT Id FROM Account")) == 1
    assert transport.calls == 2


def test_exhausted_retries_raise_api_error():
    transport = FakeTransport([(503, b"down")] * 4)
    client, _ = _client(transport, max_retries=3)
    with pytest.raises(ApiError, match="after 4 attempts"):
        client.query("SELECT Id FROM Account")
    assert transport.calls == 4  # 1 try + 3 retries


def test_auth_failure_fails_fast_without_retry():
    transport = FakeTransport([(401, b"nope"), _ok([sample_raw()])])
    client, sleeps = _client(transport)
    with pytest.raises(ApiAuthError):
        client.query("SELECT Id FROM Account")
    assert transport.calls == 1
    assert sleeps == []


def test_client_error_not_retried():
    transport = FakeTransport([(400, b"bad query"), _ok([sample_raw()])])
    client, _ = _client(transport)
    with pytest.raises(ApiError, match="HTTP 400"):
        client.query("SELECT Id FROM Account")
    assert transport.calls == 1


def test_backoff_grows_exponentially():
    transport = FakeTransport([(500, b"x")] * 3)
    sleeps = []
    client = SalesforceApiClient(
        "https://example.my.salesforce.com",
        "token",
        max_retries=2,
        backoff_base_seconds=1.0,
        request_fn=transport,
        sleep_fn=sleeps.append,
    )
    with pytest.raises(ApiError):
        client.query("SELECT Id FROM Account")
    # delays are 1.0 * 2**attempt + jitter in [0, 1): attempt 0 in [1, 2),
    # attempt 1 in [2, 3).
    assert 1.0 <= sleeps[0] < 2.0
    assert 2.0 <= sleeps[1] < 3.0


def test_paging_follows_next_records_url():
    transport = FakeTransport([
        _ok([sample_raw("1")], next_url="/services/data/v59.0/query/abc"),
        _ok([sample_raw("2")]),
    ])
    client, _ = _client(transport)
    rows = client.query("SELECT Id FROM Account")
    assert [row["Id"] for row in rows] == ["1", "2"]
    assert transport.calls == 2


def test_missing_credentials_rejected():
    with pytest.raises(ApiError):
        SalesforceApiClient("", "")


# --- SyntheticApiClient ---


def test_synthetic_full_load(tmp_path):
    (tmp_path).mkdir(exist_ok=True)
    (tmp_path / "account.json").write_text(json.dumps([sample_raw()]))
    rows = SyntheticApiClient(tmp_path).fetch("Account", None)
    assert len(rows) == 1


def test_synthetic_filters_by_since(tmp_path):
    (tmp_path / "account.json").write_text(json.dumps([
        sample_raw("1", "2026-11-01T10:00:00Z"),
        sample_raw("2", "2026-11-09T10:00:00Z"),
    ]))
    since = datetime(2026, 11, 5, tzinfo=timezone.utc)
    rows = SyntheticApiClient(tmp_path).fetch("Account", since)
    assert [row["Id"] for row in rows] == ["2"]


def test_synthetic_missing_file_raises(tmp_path):
    with pytest.raises(ApiError, match="no synthetic data"):
        SyntheticApiClient(tmp_path).fetch("Account", None)
