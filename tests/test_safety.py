"""آزمون لایهٔ ایمنی — حالت‌ها، قفل‌ها و توقف اضطراری."""
from __future__ import annotations

import pytest

from omid.errors import SafetyError
from omid.safety.modes import (
    CONTROL_CONFIRM_PHRASE,
    ESTOP_RELEASE_PHRASE,
    SafetyManager,
)


def make(**kwargs) -> SafetyManager:
    audit_calls: list = []
    mgr = SafetyManager(audit=lambda *a, **k: audit_calls.append((a, k)), **kwargs)
    mgr.audit_calls = audit_calls  # type: ignore[attr-defined]
    return mgr


def test_default_mode_is_simulate():
    mgr = make(requested_mode="simulate")
    assert mgr.mode == "simulate"


def test_control_downgraded_when_not_allowed():
    mgr = make(requested_mode="control", allow_physical_control=False)
    assert mgr.mode == "simulate"  # تنزل امن
    assert any("downgraded" in c[0][0] for c in mgr.audit_calls)


def test_control_requires_confirm_phrase():
    mgr = make(requested_mode="simulate", allow_physical_control=True)
    with pytest.raises(SafetyError):
        mgr.request_mode("control", confirm="")
    with pytest.raises(SafetyError):
        mgr.request_mode("control", confirm="please")
    assert mgr.request_mode("control", confirm=CONTROL_CONFIRM_PHRASE) == "control"


def test_control_refused_when_config_locked():
    mgr = make(requested_mode="simulate", allow_physical_control=False)
    with pytest.raises(SafetyError):
        mgr.request_mode("control", confirm=CONTROL_CONFIRM_PHRASE)


def test_invalid_mode_rejected():
    mgr = make()
    with pytest.raises(SafetyError):
        mgr.request_mode("yolo")


def test_risk_gates_per_mode():
    mgr = make(requested_mode="observe")
    mgr.assert_allowed("read")
    with pytest.raises(SafetyError):
        mgr.assert_allowed("suggest")
    with pytest.raises(SafetyError):
        mgr.assert_allowed("simulate")

    mgr.request_mode("simulate")
    mgr.assert_allowed("read")
    mgr.assert_allowed("suggest")
    mgr.assert_allowed("simulate")
    with pytest.raises(SafetyError):
        mgr.assert_allowed("physical")


def test_estop_is_always_possible_and_blocks_risky_ops():
    mgr = make(requested_mode="simulate", allow_physical_control=True)
    snapshot = mgr.trigger_estop("test")
    assert snapshot["estop_active"] is True
    assert mgr.mode == "observe"
    mgr.assert_allowed("read")  # مشاهده همیشه مجاز
    with pytest.raises(SafetyError):
        mgr.assert_allowed("simulate")
    with pytest.raises(SafetyError):
        mgr.assert_allowed("physical")


def test_estop_blocks_mode_escalation():
    mgr = make(requested_mode="simulate", allow_physical_control=True)
    mgr.trigger_estop("x")
    with pytest.raises(SafetyError):
        mgr.request_mode("control", confirm=CONTROL_CONFIRM_PHRASE)
    with pytest.raises(SafetyError):
        mgr.request_mode("simulate")


def test_estop_release_requires_confirm_and_stays_observe():
    mgr = make(requested_mode="simulate", allow_physical_control=True)
    mgr.trigger_estop("x")
    with pytest.raises(SafetyError):
        mgr.release_estop("wrong")
    snapshot = mgr.release_estop(ESTOP_RELEASE_PHRASE)
    assert snapshot["estop_active"] is False
    assert snapshot["mode"] == "observe"  # ارتقا نیازمند درخواست جداگانه


def test_transitions_are_audited():
    mgr = make()
    mgr.request_mode("observe")
    types = [c[0][0] for c in mgr.audit_calls]
    assert "safety.mode_changed" in types
    mgr.trigger_estop("reason")
    assert "safety.estop_triggered" in [c[0][0] for c in mgr.audit_calls]
    severities = [c[1].get("severity") for c in mgr.audit_calls]
    assert "critical" in severities
