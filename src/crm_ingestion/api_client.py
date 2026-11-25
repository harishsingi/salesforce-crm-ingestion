"""CRM API access with retries and backoff.

Two clients share one interface:

- :class:`SalesforceApiClient` talks to the real Salesforce REST API
  (``/services/data/<version>/query``) with a Bearer token. Transient
  failures (HTTP 429, 5xx, network errors, timeouts) are retried with
  exponential backoff plus jitter; auth failures and other 4xx errors
  fail fast because retrying them cannot help.
- :class:`SyntheticApiClient` is the offline stand-in used when no
  credentials are configured: it reads the synthetic generator output
  and applies the same ``since`` filter the real query would. It lets the
  whole pipeline run locally with no account and no network.

Both return plain API-shaped dicts; validation happens downstream in
:mod:`crm_ingestion.validate`, exactly as the SRC schema check does in
production.
"""

from __future__ import annotations

import json
import logging
import random
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Protocol

from .errors import ApiAuthError, ApiError
from .models import format_timestamp, parse_timestamp

logger = logging.getLogger(__name__)

API_VERSION = "v59.0"

#: HTTP statuses worth retrying: rate limiting and server-side failures.
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


class RequestFn(Protocol):
    """Callable performing one HTTP request; returns (status, body bytes)."""

    def __call__(self, url: str, headers: dict[str, str]) -> tuple[int, bytes]: ...


def _urllib_request(url: str, headers: dict[str, str], timeout: float) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except urllib.error.URLError as exc:
        raise ApiError(f"network error calling {url}: {exc.reason}") from exc


class SalesforceApiClient:
    """Salesforce REST API client with retry/backoff and paging."""

    def __init__(
        self,
        instance_url: str,
        access_token: str,
        max_retries: int = 3,
        backoff_base_seconds: float = 1.0,
        timeout_seconds: float = 30.0,
        request_fn: RequestFn | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        if not instance_url or not access_token:
            raise ApiError("instance_url and access_token are both required")
        self.instance_url = instance_url.rstrip("/")
        self.access_token = access_token
        self.max_retries = max_retries
        self.backoff_base_seconds = backoff_base_seconds
        self.timeout_seconds = timeout_seconds
        self._request = request_fn or (
            lambda url, headers: _urllib_request(url, headers, timeout_seconds)
        )
        self._sleep = sleep_fn

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        }

    def _get_with_retries(self, url: str) -> dict[str, Any]:
        """GET with retries on transient failures; returns the JSON body."""
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                status, body = self._request(url, self._headers())
            except ApiError as exc:
                last_error = exc
                status, body = None, b""
            if status is not None:
                if status == 200:
                    try:
                        return json.loads(body.decode("utf-8"))
                    except ValueError as exc:
                        raise ApiError(f"API returned invalid JSON from {url}") from exc
                if status in (401, 403):
                    raise ApiAuthError(
                        f"Salesforce auth failed (HTTP {status}); "
                        "check the access token, do not retry"
                    )
                if status not in RETRYABLE_STATUSES:
                    raise ApiError(f"Salesforce query failed (HTTP {status}): {body[:200]!r}")
                last_error = ApiError(f"Salesforce query failed (HTTP {status})")
            if attempt < self.max_retries:
                delay = self.backoff_base_seconds * (2**attempt) + random.uniform(0, 1)
                logger.warning(
                    "api request failed (attempt %d/%d): %s; retrying in %.1fs",
                    attempt + 1,
                    self.max_retries + 1,
                    last_error,
                    delay,
                )
                self._sleep(delay)
        raise ApiError(
            f"Salesforce query failed after {self.max_retries + 1} attempts: {last_error}"
        )

    def query(self, soql: str) -> list[dict[str, Any]]:
        """Run a SOQL query and return all records, following paging."""
        from urllib.parse import quote

        url = (
            f"{self.instance_url}/services/data/{API_VERSION}/query"
            f"?q={quote(soql)}"
        )
        records: list[dict[str, Any]] = []
        while url:
            payload = self._get_with_retries(url)
            records.extend(payload.get("records", []))
            next_url = payload.get("nextRecordsUrl")
            url = f"{self.instance_url}{next_url}" if next_url else ""
            if url:
                logger.debug("following paged query: %s", next_url)
        logger.info("api query returned rows=%d", len(records))
        return records


class SyntheticApiClient:
    """Offline stand-in for the API: reads generated synthetic records.

    Applies the same ``since`` filter the real SOQL query would, so the
    downloader behaves identically in both modes. Raises :class:`ApiError`
    when no synthetic file exists for the requested object.
    """

    def __init__(self, synthetic_dir: str | Path) -> None:
        self.synthetic_dir = Path(synthetic_dir)

    def fetch(
        self, object_name: str, since: datetime | None
    ) -> list[dict[str, Any]]:
        path = self.synthetic_dir / f"{object_name.lower()}.json"
        if not path.exists():
            raise ApiError(
                f"no synthetic data for {object_name} at {path}; "
                "run generate_data first or configure the real API"
            )
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise ApiError(f"synthetic file {path} is not valid JSON: {exc}") from exc
        if not isinstance(raw, list):
            raise ApiError(f"synthetic file {path} must hold a JSON list")
        if since is None:
            logger.info("synthetic fetch object=%s rows=%d (full load)", object_name, len(raw))
            return raw
        kept = [
            row
            for row in raw
            if parse_timestamp(row["LastModifiedDate"]) >= since
        ]
        logger.info(
            "synthetic fetch object=%s since=%s rows=%d/%d",
            object_name,
            format_timestamp(since),
            len(kept),
            len(raw),
        )
        return kept
