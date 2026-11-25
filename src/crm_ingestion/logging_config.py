"""Logging setup: one shared format for every stage.

All stages log instead of printing, so a run can be shipped to a log
aggregator and so row counts are greppable (``rows_in=``, ``rows_out=``,
``rejected=``) instead of buried in free text.
"""

from __future__ import annotations

import logging
import sys

DEFAULT_FORMAT = "%(asctime)s %(levelname)-8s %(name)s %(message)s"


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure the root logger once and return the pipeline logger."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=DEFAULT_FORMAT,
        stream=sys.stdout,
    )
    return logging.getLogger("crm_ingestion")


def get_logger(name: str) -> logging.Logger:
    """Return a child logger for a module (``crm_ingestion.<module>``)."""
    return logging.getLogger(f"crm_ingestion.{name}")
