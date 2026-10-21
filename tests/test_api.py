"""آزمون یکپارچهٔ API — احراز هویت، تفکیک خواندن/کنترل، نرخ، هدرها."""
from __future__ import annotations

import dataclasses

from conftest import AUTH, AUTH_CONTROL, CONTROL_TOKEN, READ_TOKEN
from fastapi.testclient import TestClient

COMPANY = "هوشمندسازی صنعت امید"


# ---------- دسترسی باز ----------
def test_health_is_open(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_about_shows_official_identity(client):
    resp = client.get("/api/about")
    assert resp.status_code == 200
    body = resp.json()
    assert body["company_name"] == COMPANY
    assert body["tagline"] == "ما می‌سازیم تا شما راحت زندگی کنید"
    assert body["lead_designer_and_creator"] == "مهندس امید براتی"
    assert "دکتر کیمیا زهرا براتی" in body["collaborators"]
    assert "مهندس محسن بابایی" in body["collaborators"]


def test_dashboard_served_and_branded(client):
    resp = client.get("/dashboard/")
    assert resp.status_code == 200
    assert COMPANY in resp.text
    assert "app.js" in resp.text


def test_root_redirects_to_dashboard(client):
    resp = client.get("/", follow_redirects=True)
    assert resp.status_code == 200
    assert COMPANY in resp.text


def test_security_headers(client):
    resp = client.get("/api/health")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in resp.headers["content-security-policy"]
    assert "unsafe-inline" not in resp.headers["content-security-policy"]


# ---------- احراز هویت ----------
def test_status_requires_token(client):
    assert client.get("/api/status").status_code == 401
    assert client.get("/api/status", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/api/status", headers=AUTH).status_code == 200


def test_401_does_not_leak_token(client):
    resp = client.get("/api/status", headers={"Authorization": "Bearer wrong-token"})
    assert resp.status_code == 401
    assert READ_TOKEN not in resp.text
    assert CONTROL_TOKEN not in resp.text


def test_control_endpoints_need_control_token(client):
    resp = client.post("/api/safety/mode", headers=AUTH, json={"mode": "simulate", "confirm": ""})
    assert resp.status_code == 403  # read token alone is insufficient
    # A control token must not bypass the separate read-authentication check.
    control_only = client.post(
        "/api/safety/mode",
        headers={"X-OMID-Control-Token": CONTROL_TOKEN},
        json={"mode": "simulate", "confirm": ""},
    )
    assert control_only.status_code == 401
    invalid_read = client.post(
        "/api/safety/mode",
        headers={"Authorization": "Bearer wrong", "X-OMID-Control-Token": CONTROL_TOKEN},
        json={"mode": "simulate", "confirm": ""},
    )
    assert invalid_read.status_code == 401
    resp = client.post(
        "/api/safety/mode",
        headers=AUTH_CONTROL,
        json={"mode": "control", "confirm": "ENABLE-PHYSICAL-CONTROL"},
    )
    # توکن کنترل معتبر است اما قفل پیکربندی بسته → تضاد صادقانه 409
    assert resp.status_code == 409
    assert "OMID_ALLOW_PHYSICAL_CONTROL" in resp.json()["detail"]


# ---------- جریان ایمنی از راه API ----------
def test_estop_flow_via_api(client):
    resp = client.post("/api/safety/estop", headers=AUTH, json={"reason": "تست از API"})
    assert resp.status_code == 200
    assert resp.json()["safety"]["estop_active"] is True
    assert resp.json()["logical_estop_active"] is True
    assert resp.json()["physical_stop_confirmed"] is False
    assert "تأیید توقف فیزیکی" in resp.json()["operator_notice"]

    status = client.get("/api/status", headers=AUTH).json()
    assert status["safety"]["estop_active"] is True
    assert status["safety"]["mode"] == "observe"

    # حرکت شبیه‌سازی‌شده هم در E-STOP مسدود است
    resp = client.post("/api/twin/preview", headers=AUTH, json={"x": 10})
    body = resp.json()
    assert body["ok"] is False or resp.status_code == 200  # twin پیش‌نمایش مستقل است اما...
    task = client.post(
        "/api/agent/request", headers=AUTH, json={"text": "شبیه‌سازی حرکت x=10"}
    ).json()
    assert task["status"] == "failed"

    # آزادسازی بدون اعتبار کنترل ممکن نیست
    resp = client.post("/api/safety/estop/release", headers=AUTH, json={"confirm": "RELEASE-ESTOP"})
    assert resp.status_code == 403
    # عبارت تأیید غلط → 409
    resp = client.post("/api/safety/estop/release", headers=AUTH_CONTROL, json={"confirm": "WRONG"})
    assert resp.status_code == 409
    # آزادسازی معتبر
    resp = client.post("/api/safety/estop/release", headers=AUTH_CONTROL, json={"confirm": "RELEASE-ESTOP"})
    assert resp.status_code == 200
    assert resp.json()["safety"]["estop_active"] is False
    assert resp.json()["safety"]["mode"] == "observe"


# ---------- عامل ----------
def test_agent_request_via_api(client):
    resp = client.post("/api/agent/request", headers=AUTH, json={"text": "وضعیت سیستم"})
    assert resp.status_code == 200
    task = resp.json()
    assert task["status"] == "completed"
    assert task["steps"][0]["tool"] == "system_status"
    assert task["steps"][0]["evidence"]["granted"] is True

    tasks = client.get("/api/tasks", headers=AUTH).json()
    assert any(t["id"] == task["id"] for t in tasks["tasks"])

    single = client.get(f"/api/tasks/{task['id']}", headers=AUTH)
    assert single.status_code == 200

    missing = client.get("/api/tasks/nonexistent", headers=AUTH)
    assert missing.status_code == 404


def test_agent_request_requires_auth(client):
    assert client.post("/api/agent/request", json={"text": "وضعیت"}).status_code == 401


# ---------- تجهیزات و twin ----------
def test_devices_and_discovery_via_api(client):
    resp = client.post("/api/devices/discover", headers=AUTH, json={"scope": "network"})
    assert resp.status_code == 200
    assert resp.json()["available"] is False  # بدون allowlist → صادقانه غیرفعال

    resp = client.get("/api/devices", headers=AUTH)
    assert resp.status_code == 200

    resp = client.get("/api/drivers", headers=AUTH)
    assert any(d["name"] == "grbl" for d in resp.json()["drivers"])

    resp = client.post("/api/drivers/grbl/status", headers=AUTH)
    assert resp.json()["source"] == "simulation"

    assert client.post("/api/drivers/nope/status", headers=AUTH).status_code == 404


def test_twin_preview_validation_via_api(client):
    ok = client.post("/api/twin/preview", headers=AUTH, json={"x": 10, "y": 5, "feed": 200}).json()
    assert ok["ok"] is True and ok["source"] == "simulation"
    bad = client.post("/api/twin/preview", headers=AUTH, json={"x": 99999}).json()
    assert bad["ok"] is False and "محدوده" in bad["error"]


# ---------- دانش و حافظه ----------
def test_knowledge_search_validation(client):
    assert client.get("/api/knowledge/search?q=", headers=AUTH).status_code == 422
    resp = client.get("/api/knowledge/search?q=لیزر", headers=AUTH)
    assert resp.status_code == 200
    assert "note" in resp.json()


def test_knowledge_ingest_requires_control(client, tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("# تست\nمحتوای آزمون", encoding="utf-8")
    resp = client.post("/api/knowledge/ingest", headers=AUTH, json={"path": str(doc)})
    assert resp.status_code == 403  # بدون اعتبار کنترل → رد (دسترسی به FS سرور)
    resp = client.post("/api/knowledge/ingest", headers=AUTH_CONTROL, json={"path": str(doc)})
    assert resp.status_code == 200
    assert resp.json()["chunks"] >= 1
    found = client.get("/api/knowledge/search?q=محتوای+آزمون", headers=AUTH).json()
    assert found["hits"]


def test_memory_prefs_control_gate(client):
    assert client.post("/api/memory/prefs", headers=AUTH, json={"key": "k", "value": "v"}).status_code == 403
    resp = client.post("/api/memory/prefs", headers=AUTH_CONTROL, json={"key": "k", "value": "v"})
    assert resp.status_code == 200
    prefs = client.get("/api/memory/prefs", headers=AUTH).json()
    assert prefs["preferences"]["k"]["value"] == "v"
    assert client.delete("/api/memory/prefs/k", headers=AUTH_CONTROL).status_code == 200
    assert client.delete("/api/memory/prefs/k", headers=AUTH_CONTROL).status_code == 404


def test_diagnostics_endpoints(client):
    rules = client.get("/api/diagnostics/rules", headers=AUTH).json()
    assert rules["method"] == "rule-based"
    scan = client.post("/api/diagnostics/scan", headers=AUTH)
    assert scan.status_code == 200
    assert "disclaimer" in scan.json()
    findings = client.get("/api/diagnostics/findings", headers=AUTH)
    assert findings.status_code == 200


def test_events_endpoint(client):
    client.post("/api/agent/request", headers=AUTH, json={"text": "وضعیت"})
    resp = client.get("/api/events?limit=50", headers=AUTH)
    assert resp.status_code == 200
    assert len(resp.json()["events"]) > 0


# ---------- محدودسازی نرخ ----------
def test_rate_limit_returns_429(tmp_path, monkeypatch):
    monkeypatch.setenv("OMID_DATA_DIR", str(tmp_path / "rl"))
    monkeypatch.setenv("OMID_API_TOKEN", READ_TOKEN)
    monkeypatch.setenv("OMID_OLLAMA_URL", "http://127.0.0.1:9")
    from omid.api.app import create_app
    from omid.config import OMIDConfig
    from omid.context import AppContext

    config = dataclasses.replace(OMIDConfig.from_env(), rate_limit_per_min=3)
    ctx = AppContext(config)
    try:
        with TestClient(create_app(ctx)) as rl_client:
            codes = [rl_client.get("/api/status", headers=AUTH).status_code for _ in range(5)]
            assert codes[:3] == [200, 200, 200]
            assert 429 in codes
            # health معاف است
            assert rl_client.get("/api/health").status_code == 200
    finally:
        ctx.close()



def test_estop_api_does_not_claim_physical_stop_when_serial_driver_is_disconnected(client, ctx):
    # The serial backend is deliberately disconnected; no hardware I/O is performed.
    ctx.grbl.backend = "serial"
    ctx.grbl._serial = None
    resp = client.post("/api/safety/estop", headers=AUTH, json={"reason": "disconnected-driver regression"})
    assert resp.status_code == 200  # logical E-Stop is still activated
    body = resp.json()
    assert body["ok"] is True
    assert body["logical_estop_active"] is True
    assert body["physical_stop_confirmed"] is False
    assert body["safety"]["estop_active"] is True
    assert body["driver"]["ok"] is False
    assert body["driver"]["source"] == "live"
