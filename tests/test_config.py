"""Tests for crm_ingestion.config: YAML loading and env overrides."""

import os

import pytest

from crm_ingestion.config import Settings
from crm_ingestion.errors import ConfigError


def test_defaults_when_no_config_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CRM_CONFIG", raising=False)
    settings = Settings.load()
    assert settings.objects == ["Account", "Opportunity", "Contact"]
    assert settings.overlap_minutes == 15
    assert settings.dq_max_age_hours == 36
    assert settings.use_real_api is False


def test_yaml_values_applied(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(
        "objects:\n  - Account\noverlap_minutes: 30\ndq_max_age_hours: 12\n"
    )
    settings = Settings.load(config)
    assert settings.objects == ["Account"]
    assert settings.overlap_minutes == 30
    assert settings.dq_max_age_hours == 12


def test_unknown_key_rejected(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("bogus_key: 1\n")
    with pytest.raises(ConfigError, match="unknown keys"):
        Settings.load(config)


def test_invalid_yaml_rejected(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("objects: [unclosed\n")
    with pytest.raises(ConfigError):
        Settings.load(config)


def test_missing_explicit_config_rejected(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        Settings.load(tmp_path / "missing.yaml")


def test_env_credentials_enable_real_api(monkeypatch):
    monkeypatch.setenv("SF_INSTANCE_URL", "https://example.my.salesforce.com")
    monkeypatch.setenv("SF_ACCESS_TOKEN", "token-123")
    settings = Settings.load()
    assert settings.use_real_api is True


def test_half_credentials_rejected(monkeypatch):
    monkeypatch.setenv("SF_INSTANCE_URL", "https://example.my.salesforce.com")
    monkeypatch.delenv("SF_ACCESS_TOKEN", raising=False)
    with pytest.raises(ConfigError, match="must be set together"):
        Settings.load()


def test_negative_overlap_rejected():
    with pytest.raises(ConfigError):
        Settings(overlap_minutes=-1)._validate()
