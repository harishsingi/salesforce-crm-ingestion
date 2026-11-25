"""End-to-end local run: generate -> download -> SRC->PRE -> PRE->SEM -> DQ.

This is the offline demo of the full pipeline. In production each stage
is its own Glue job / scheduled step; here they run in sequence so the
whole flow can be exercised with one command.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from . import dq_check, download, generate_data, pre_to_sem, src_to_pre
from .config import Settings
from .logging_config import setup_logging

logger = logging.getLogger(__name__)


def run(settings: Settings, objects: list[str]) -> dict[str, dict]:
    """Run every stage for each object; returns per-object row counts."""
    summary: dict[str, dict] = {}
    for object_name in objects:
        logger.info("pipeline start object=%s", object_name)
        if object_name.lower() == "account":
            rows = generate_data.generate()
            synth_path = Path(settings.synthetic_dir)
            synth_path.mkdir(parents=True, exist_ok=True)
            (synth_path / "account.json").write_text(
                json.dumps(rows, indent=2) + "\n", encoding="utf-8"
            )
            logger.info("generated rows=%d", len(rows))
        downloaded = download.run(settings, object_name)
        upserted = src_to_pre.run(settings, object_name)
        promoted = pre_to_sem.run(settings, object_name)
        dq = dq_check.run(settings, object_name)
        summary[object_name] = {
            "downloaded": downloaded.rows_valid,
            "rejected": downloaded.rows_rejected,
            "pre_rows": upserted.pre_after,
            "sem_rows": promoted.sem_out,
            "deletes_applied": promoted.deletes_applied,
            "dq_status": dq.status,
        }
        logger.info("pipeline done object=%s summary=%s", object_name, summary[object_name])
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the full pipeline locally.")
    parser.add_argument("--object", action="append", default=None,
                        help="object to run (repeatable; default: Account)")
    parser.add_argument("--config", default=None, help="path to config.yaml")
    args = parser.parse_args()
    settings = Settings.load(args.config)
    setup_logging(settings.log_level)
    run(settings, args.object or ["Account"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
