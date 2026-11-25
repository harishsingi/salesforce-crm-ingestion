"""Downloader: watermark -> query -> API fetch -> land JSON raw.

For one object:
1. Read the watermark (Athena MAX timestamp on the target; locally the
   PRE file's MAX LastModifiedDate).
2. Build the incremental query from the watermark, with a small overlap.
3. Fetch from the API (real Salesforce when credentials are configured,
   otherwise the synthetic offline client) and land the response as JSON
   in the raw layer, exactly as returned, overwriting that day's file.
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from .api_client import SalesforceApiClient, SyntheticApiClient
from .config import Settings
from .logging_config import get_logger, setup_logging
from .models import format_timestamp
from .store import layer_path, write_records
from .validate import validate_records, write_quarantine
from .watermark import build_soql, watermark_from_file

logger = get_logger("download")


@dataclass
class DownloadResult:
    """Row counts for one download run."""

    object_name: str
    watermark: str | None
    rows_fetched: int
    rows_valid: int
    rows_rejected: int
    raw_path: Path


def build_client(settings: Settings):
    """Real API client when credentials exist, else the synthetic stand-in."""
    if settings.use_real_api:
        logger.info("using real Salesforce API (instance configured)")
        return SalesforceApiClient(
            instance_url=settings.salesforce_instance_url or "",
            access_token=settings.salesforce_access_token or "",
            max_retries=settings.max_retries,
            backoff_base_seconds=settings.backoff_base_seconds,
            timeout_seconds=settings.request_timeout_seconds,
        )
    logger.info("no Salesforce credentials configured; using synthetic offline API")
    return SyntheticApiClient(settings.synthetic_dir)


def run(settings: Settings, object_name: str, client=None) -> DownloadResult:
    """Download one object incrementally. Returns row counts."""
    pre_path = layer_path(settings.pre_dir, object_name)
    watermark = watermark_from_file(pre_path)
    overlap = timedelta(minutes=settings.overlap_minutes)
    soql = build_soql(object_name, watermark, overlap)
    logger.info(
        "download object=%s watermark=%s soql=%s",
        object_name,
        format_timestamp(watermark) if watermark else "none (full load)",
        soql,
    )

    client = client or build_client(settings)
    if isinstance(client, SyntheticApiClient):
        since = watermark - overlap if watermark else None
        raw_rows = client.fetch(object_name, since)
    else:
        raw_rows = client.query(soql)

    # Schema check happens here (SRC), before anything is landed as clean.
    validated = validate_records(raw_rows)
    quarantine_path = None
    if validated.rejected:
        quarantine_path = write_quarantine(
            validated.rejected,
            layer_path(settings.quarantine_dir, object_name).with_suffix(".jsonl"),
        )

    raw_path = layer_path(settings.raw_dir, object_name)
    write_records(raw_path, validated.valid)
    logger.info(
        "download done object=%s rows_fetched=%d rows_valid=%d rows_rejected=%d "
        "raw_path=%s quarantine=%s",
        object_name,
        len(raw_rows),
        len(validated.valid),
        len(validated.rejected),
        raw_path,
        quarantine_path or "none",
    )
    return DownloadResult(
        object_name=object_name,
        watermark=format_timestamp(watermark) if watermark else None,
        rows_fetched=len(raw_rows),
        rows_valid=len(validated.valid),
        rows_rejected=len(validated.rejected),
        raw_path=raw_path,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Download one CRM object (raw layer).")
    parser.add_argument("--object", default="Account", help="Salesforce object, e.g. Account")
    parser.add_argument("--config", default=None, help="path to config.yaml")
    args = parser.parse_args()
    settings = Settings.load(args.config)
    setup_logging(settings.log_level)
    run(settings, args.object)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
