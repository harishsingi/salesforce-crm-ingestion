"""Generate synthetic CRM records. No real customer data.

Deterministic for a given seed and date: 100 accounts spread over the
last 28 days, plus one exact duplicate re-fetch and one update (same Id,
newer timestamp, changed amount) to exercise dedupe. Dates are relative
to the run date so the data is always fresh for the DQ check; nothing
here is backdated or presented as real.
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from .logging_config import get_logger, setup_logging

logger = get_logger("generate_data")

DEFAULT_COUNT = 100
DEFAULT_SEED = 42
RECORD_DAYS = 28  # records spread over the last 28 days


def generate(
    count: int = DEFAULT_COUNT,
    seed: int = DEFAULT_SEED,
    base_date: date | None = None,
) -> list[dict[str, Any]]:
    """Build synthetic Account records, API-shaped.

    Args:
        count: number of distinct accounts to generate.
        seed: random seed; the same seed and date give the same output.
        base_date: the "today" the data is relative to (defaults to today).
    """
    base_date = base_date or date.today()
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    for i in range(1, count + 1):
        day = base_date - timedelta(days=RECORD_DAYS - 1 - (i % RECORD_DAYS))
        moment = datetime.combine(day, time(0, 0, 0), tzinfo=timezone.utc)
        rows.append(
            {
                "Id": f"001{i:04d}",
                "Name": f"Account {i}",
                "LastModifiedDate": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "IsDeleted": "false",
                "Amount": rng.randint(1000, 90000),
            }
        )
    # One duplicate re-fetch and one update, to exercise dedupe.
    if len(rows) >= 2:
        rows.append(dict(rows[0]))
        update_moment = datetime.combine(base_date, time(0, 0, 0), tzinfo=timezone.utc)
        rows.append(
            {
                **rows[1],
                "LastModifiedDate": update_moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "Amount": 91000,
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate synthetic CRM records.")
    parser.add_argument("--out", default="data/synthetic", help="output directory")
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()
    setup_logging()
    rows = generate(count=args.count, seed=args.seed)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "account.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    logger.info("generated rows=%d path=%s", len(rows), out / "account.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
