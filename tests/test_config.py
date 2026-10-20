"""آزمون پیکربندی — پیش‌فرض‌های امن و اعتبارسنجی."""
from __future__ import annotations

import json

import pytest

from omid.config import OMIDConfig
from omid.errors import ConfigError


def test_defaults_are_safe(monkeypatch):
    monkeypatch.delenv("OMID_MODE", raising=False)
    monkeypatch.delenv("OMID_ALLOW_PHYSICAL_CONTROL", raising=False)
    cfg = OMIDConfig.from_env()
    assert cfg.mode == "simulate"
    assert cfg.allow_physical_control is False
    assert cfg.api_token is None
    assert cfg.control_token is None
    assert cfg.network_allowlist == ()  # بدون allowlist → بدون اسکن


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


def test_machine_limits_check():
    cfg = OMIDConfig()
    cfg.limits.check_axis("x", 100)
    with pytest.raises(ConfigError):
        cfg.limits.check_axis("x", 99999)
