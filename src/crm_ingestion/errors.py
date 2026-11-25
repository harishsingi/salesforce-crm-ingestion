"""Error types for the CRM ingestion pipeline.

Every failure that a stage can report has its own type so callers (and
tests) can tell a bad record from a failed API call from a stale target,
instead of catching a bare ``Exception``.
"""


class CrmIngestionError(Exception):
    """Base class for all pipeline errors."""


class ConfigError(CrmIngestionError):
    """The configuration file or environment is missing or invalid."""


class SchemaValidationError(CrmIngestionError):
    """A record fails schema validation. Carries the offending field."""

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


class ApiError(CrmIngestionError):
    """The CRM API call failed, including after all retries were spent."""


class ApiAuthError(ApiError):
    """Authentication failed (HTTP 401/403). Retrying will not help."""


class WatermarkError(CrmIngestionError):
    """The watermark (latest loaded timestamp) could not be determined."""


class DqAlertError(CrmIngestionError):
    """A data-quality check failed: the target is empty or stale."""
