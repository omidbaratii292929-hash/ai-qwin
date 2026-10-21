"""آزمون پیکربندی — پیش‌فرض‌های امن و اعتبارسنجی."""
from __future__ import annotations

import json

import pytest

from omid.config import OMIDConfig
from omid.errors import ConfigError


def test_defaults_are_safe(monkeypatch):
    monkeypatch.delenv("OMID_MODE", raising=False)
    monkeypatch.delenv("OMID_ALLOW_PHYSICAL_CONTROL", raising=False)
    monkeypatch.delenv("OMID_GRBL_BACKEND", raising=False)
    monkeypatch.delenv("OMID_GRBL_SERIAL_PORT", raising=False)
    monkeypatch.delenv("OMID_GRBL_BAUDRATE", raising=False)
    cfg = OMIDConfig.from_env()
    assert cfg.mode == "simulate"
    assert cfg.allow_physical_control is False
    assert cfg.api_token is None
    assert cfg.control_token is None
    assert cfg.network_allowlist == ()  # بدون allowlist → بدون اسکن
    assert cfg.grbl_backend == "simulated"
    assert cfg.grbl_serial_port is None
    assert cfg.grbl_baudrate == 115200


def test_invalid_mode_rejected():
    with pytest.raises(ConfigError):
        OMIDConfig(mode="destroy")


def test_invalid_port_rejected():
    with pytest.raises(ConfigError):
        OMIDConfig(api_port=70000)


def test_invalid_lang_rejected():
    with pytest.raises(ConfigError):
        OMIDConfig(lang="fr")


def test_public_view_has_no_secrets(monkeypatch):
    monkeypatch.setenv("OMID_API_TOKEN", "super-secret-read")
    monkeypatch.setenv("OMID_CONTROL_TOKEN", "super-secret-control")
    cfg = OMIDConfig.from_env()
    view = json.dumps(cfg.public_view(), ensure_ascii=False)
    assert "super-secret" not in view
    assert cfg.public_view()["api_token_configured"] is True


def test_grbl_backend_validation_and_explicit_serial_port():
    with pytest.raises(ConfigError, match="OMID_GRBL_BACKEND"):
        OMIDConfig(grbl_backend="auto")
    with pytest.raises(ConfigError, match="OMID_GRBL_SERIAL_PORT"):
        OMIDConfig(grbl_backend="serial")
    with pytest.raises(ConfigError, match="OMID_GRBL_BAUDRATE"):
        OMIDConfig(grbl_baudrate=0)


def test_grbl_serial_settings_read_from_environment(monkeypatch):
    monkeypatch.setenv("OMID_GRBL_BACKEND", "serial")
    monkeypatch.setenv("OMID_GRBL_SERIAL_PORT", "COM_TEST")
    monkeypatch.setenv("OMID_GRBL_BAUDRATE", "115200")
    cfg = OMIDConfig.from_env()
    assert cfg.grbl_backend == "serial"
    assert cfg.grbl_serial_port == "COM_TEST"
    assert cfg.grbl_baudrate == 115200


def test_machine_limits_check():
    cfg = OMIDConfig()
    cfg.limits.check_axis("x", 100)
    with pytest.raises(ConfigError):
        cfg.limits.check_axis("x", 99999)


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.20", "omid-host.local"])
def test_non_loopback_api_requires_read_token(host):
    with pytest.raises(ConfigError, match="OMID_API_TOKEN"):
        OMIDConfig(api_host=host)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_loopback_api_can_run_without_read_token(host):
    cfg = OMIDConfig(api_host=host)
    assert cfg.api_token is None


def test_non_loopback_api_with_read_token_is_allowed():
    cfg = OMIDConfig(api_host="0.0.0.0", api_token="test-read-token")
    assert cfg.api_host == "0.0.0.0"
    assert cfg.api_token == "test-read-token"


def test_environment_non_loopback_host_requires_read_token(monkeypatch):
    monkeypatch.setenv("OMID_API_HOST", "0.0.0.0")
    monkeypatch.delenv("OMID_API_TOKEN", raising=False)
    with pytest.raises(ConfigError, match="OMID_API_TOKEN"):
        OMIDConfig.from_env()
