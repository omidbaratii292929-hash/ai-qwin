"""آزمون CLI و خودآزمایی — شواهد قابل‌اجرا برای CI."""
from __future__ import annotations

import json

import pytest


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("OMID_DATA_DIR", str(tmp_path / "cli-data"))
    monkeypatch.setenv("OMID_OLLAMA_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("OMID_OLLAMA_MODEL", "")
    monkeypatch.setenv("OMID_MODE", "simulate")


def test_selfcheck_passes(capsys):
    from omid.__main__ import main

    assert main(["selfcheck"]) == 0
    out = capsys.readouterr().out
    report = json.loads(out[: out.rindex("}") + 1])
    assert report["overall_ok"] is True
    checks = report["checks"]
    assert checks["branding"]["ok"] is True
    assert checks["branding"]["detail"] == "هوشمندسازی صنعت امید"
    assert checks["safety"]["detail"]["mode"] == "simulate"
    assert checks["ai_ollama"]["available"] is False  # صادقانه: Ollama اینجا نصب نیست
    assert "serial_support" in checks
    assert "SELF-CHECK: PASS" in out


def test_brand_command(capsys):
    from omid.__main__ import main

    assert main(["brand"]) == 0
    out = capsys.readouterr().out
    assert "هوشمندسازی صنعت امید" in out
    assert "ما می‌سازیم تا شما راحت زندگی کنید" in out
    assert "مهندس امید براتی" in out


def test_request_command(capsys):
    from omid.__main__ import main

    assert main(["request", "وضعیت سیستم را بررسی کن"]) == 0
    out = capsys.readouterr().out
    payload = json.loads(out[: out.rindex("}") + 1])
    assert payload["status"] == "completed"
    assert payload["steps"][0]["tool"] == "system_status"
    assert "خلاصه" in out


def test_unknown_command_exits_2():
    from omid.__main__ import main

    with pytest.raises(SystemExit) as exc:
        main(["fly"])
    assert exc.value.code == 2


def test_import_all_modules():
    """بررسی سلامت ساختار: همهٔ ماژول‌های اصلی قابل import باشند."""
    import importlib

    modules = [
        "omid", "omid.branding", "omid.config", "omid.errors", "omid.events",
        "omid.context", "omid.safety.modes", "omid.safety.validator",
        "omid.core.permissions", "omid.core.tools", "omid.core.tasks",
        "omid.core.agent", "omid.core.builtin_tools",
        "omid.ai.ollama", "omid.discovery.registry",
        "omid.drivers.base", "omid.drivers.grbl", "omid.twin.simulator",
        "omid.knowledge.rag", "omid.memory.store", "omid.diagnostics.rules",
        "omid.api.app", "omid.api.auth", "omid.api.middleware", "omid.api.schemas",
        "omid.api.routers.status", "omid.api.routers.agent", "omid.api.routers.safety",
        "omid.api.routers.devices", "omid.api.routers.knowledge",
    ]
    for name in modules:
        importlib.import_module(name)
