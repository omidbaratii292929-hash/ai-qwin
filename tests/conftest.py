"""conftest — فیکسچرهای مشترک آزمون‌ها.

دادهٔ آزمون هرگز با حافظهٔ واقعی مخلوط نمی‌شود: همه‌چیز در tmp_path
ایزوله ساخته می‌شود.

© هوشمندسازی صنعت امید — OMID Industrial AI Agent
"""
from __future__ import annotations

import pytest

READ_TOKEN = "test-read-token"
CONTROL_TOKEN = "test-control-token"
AUTH = {"Authorization": f"Bearer {READ_TOKEN}"}
AUTH_CONTROL = {**AUTH, "X-OMID-Control-Token": CONTROL_TOKEN}


@pytest.fixture()
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("OMID_MODE", "simulate")
    monkeypatch.setenv("OMID_ALLOW_PHYSICAL_CONTROL", "0")
    monkeypatch.setenv("OMID_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OMID_API_TOKEN", READ_TOKEN)
    monkeypatch.setenv("OMID_CONTROL_TOKEN", CONTROL_TOKEN)
    monkeypatch.setenv("OMID_OLLAMA_MODEL", "")  # planner قواعد-محور
    monkeypatch.setenv("OMID_OLLAMA_URL", "http://127.0.0.1:9")  # پورت بسته → health سریع و قطعی
    from omid.config import OMIDConfig

    return OMIDConfig.from_env()


@pytest.fixture()
def ctx(config):
    from omid.context import AppContext

    context = AppContext(config)
    yield context
    context.close()


@pytest.fixture()
def client(ctx):
    from fastapi.testclient import TestClient

    from omid.api.app import create_app

    app = create_app(ctx)
    with TestClient(app) as test_client:
        yield test_client
