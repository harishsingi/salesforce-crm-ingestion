"""Daily DQ check: alert when the target has no new data.

Designed to be scheduled at noon (see README for the cron line). It reads
the latest timestamp in the SEM target and fails when the target is empty
or when that timestamp is older than the configured freshness window,
meaning no new data arrived. The check is pure: ``check()`` takes the
records and a ``now`` so tests can pin the clock.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .config import Settings
from .errors import DqAlertError
from .logging_config import get_logger, setup_logging
from .models import CrmRecord
from .store import layer_path, read_validated_records
from .watermark import max_timestamp

logger = get_logger("dq_check")


@dataclass
class DqResult:
    """Outcome of one DQ check."""

    object_name: str
    status: str  # "ok", "empty", or "stale"
    latest: datetime | None
    age: timedelta | None
    record_count: int


def check(
    records: list[CrmRecord],
    object_name: str,
    max_age: timedelta,
    now: datetime | None = None,
) -> DqResult:
    """Evaluate freshness. Never raises; callers decide what to do."""
    now = now or datetime.now(timezone.utc)
    latest = max_timestamp(records)
    if latest is None:
        return DqResult(object_name, "empty", None, None, len(records))
    age = now - latest
    status = "ok" if age <= max_age else "stale"
    return DqResult(object_name, status, latest, age, len(records))


def run(
    settings: Settings, object_name: str, now: datetime | None = None
) -> DqResult:
    """Run the DQ check for one object; raises :class:`DqAlertError` on failure."""
    sem_path = layer_path(settings.sem_dir, object_name)
    records = read_validated_records(sem_path)
    result = check(
        records,
        object_name,
        timedelta(hours=settings.dq_max_age_hours),
        now=now,
    )
    if result.status == "empty":
        raise DqAlertError(f"DQ ALERT: no data in SEM for {object_name}")
    if result.status == "stale":
        raise DqAlertError(
            f"DQ ALERT: no new data for {object_name}; latest timestamp "
            f"{result.latest} is {result.age} old "
            f"(max allowed {settings.dq_max_age_hours}h)"
        )
    logger.info(
        "dq ok object=%s records=%d latest=%s age=%s",
        object_name,
        result.record_count,
        result.latest,
        result.age,
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily DQ check on the SEM target.")
    parser.add_argument("--object", default="Account", help="object, e.g. Account")
    parser.add_argument("--config", default=None, help="path to config.yaml")
    args = parser.parse_args()
    settings = Settings.load(args.config)
    setup_logging(settings.log_level)
    try:
        run(settings, args.object)
    except DqAlertError as exc:
        logger.error(str(exc))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
