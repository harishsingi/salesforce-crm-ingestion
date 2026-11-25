"""Configuration, separated from pipeline logic.

Settings come from ``config.yaml`` (checked in, no secrets) with
credentials taken only from the environment. Nothing in this module, or
anywhere else in the repo, holds a hardcoded path, token, or password.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .errors import ConfigError

DEFAULT_CONFIG_NAME = "config.yaml"

#: Only these keys are accepted in config.yaml; anything else is a typo
#: worth failing on rather than silently ignoring.
_KNOWN_KEYS = {
    "objects",
    "raw_dir",
    "pre_dir",
    "sem_dir",
    "quarantine_dir",
    "synthetic_dir",
    "overlap_minutes",
    "dq_max_age_hours",
    "max_retries",
    "backoff_base_seconds",
    "request_timeout_seconds",
    "log_level",
}


@dataclass
class Settings:
    """All pipeline settings in one place."""

    objects: list[str] = field(default_factory=lambda: ["Account", "Opportunity", "Contact"])
    raw_dir: Path = Path("data/raw")
    pre_dir: Path = Path("data/pre")
    sem_dir: Path = Path("data/sem")
    quarantine_dir: Path = Path("data/quarantine")
    synthetic_dir: Path = Path("data/synthetic")
    overlap_minutes: int = 15
    dq_max_age_hours: int = 36
    max_retries: int = 3
    backoff_base_seconds: float = 1.0
    request_timeout_seconds: float = 30.0
    log_level: str = "INFO"
    # Credentials: environment only, never config.yaml, never code.
    salesforce_instance_url: str | None = None
    salesforce_access_token: str | None = None

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> "Settings":
        """Load settings from YAML, then apply environment overrides.

        Resolution order for the file: explicit path, ``CRM_CONFIG`` env
        var, ``config.yaml`` in the working directory. A missing file is
        fine (defaults apply); a present but invalid file is an error.
        """
        path = cls._resolve_path(config_path)
        values: dict[str, Any] = {}
        if path is not None:
            values = cls._load_yaml(path)
        settings = cls(**values)
        settings.salesforce_instance_url = os.environ.get("SF_INSTANCE_URL")
        settings.salesforce_access_token = os.environ.get("SF_ACCESS_TOKEN")
        settings._validate()
        return settings

    @staticmethod
    def _resolve_path(config_path: str | Path | None) -> Path | None:
        if config_path is not None:
            candidate = Path(config_path)
            if not candidate.exists():
                raise ConfigError(f"config file not found: {candidate}")
            return candidate
        env_path = os.environ.get("CRM_CONFIG")
        if env_path:
            candidate = Path(env_path)
            if not candidate.exists():
                raise ConfigError(f"config file not found: {candidate}")
            return candidate
        default = Path(DEFAULT_CONFIG_NAME)
        return default if default.exists() else None

    @staticmethod
    def _load_yaml(path: Path) -> dict[str, Any]:
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise ConfigError(f"cannot read config file {path}: {exc}") from exc
        if loaded is None:
            return {}
        if not isinstance(loaded, dict):
            raise ConfigError(f"config file {path} must hold a YAML mapping")
        unknown = set(loaded) - _KNOWN_KEYS
        if unknown:
            raise ConfigError(f"config file {path} has unknown keys: {sorted(unknown)}")
        return loaded

    def _validate(self) -> None:
        if not self.objects:
            raise ConfigError("config must list at least one object")
        if self.overlap_minutes < 0:
            raise ConfigError("overlap_minutes must not be negative")
        if self.dq_max_age_hours <= 0:
            raise ConfigError("dq_max_age_hours must be positive")
        if self.max_retries < 0:
            raise ConfigError("max_retries must not be negative")
        if self.backoff_base_seconds < 0:
            raise ConfigError("backoff_base_seconds must not be negative")
        url, token = self.salesforce_instance_url, self.salesforce_access_token
        if bool(url) != bool(token):
            raise ConfigError(
                "SF_INSTANCE_URL and SF_ACCESS_TOKEN must be set together; "
                "with neither set the pipeline runs in offline (synthetic) mode"
            )

    @property
    def use_real_api(self) -> bool:
        """True only when both Salesforce credentials are present."""
        return bool(self.salesforce_instance_url and self.salesforce_access_token)
