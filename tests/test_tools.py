"""آزمون رجیستری ابزارها — مجوزها، timeout، kill-switch و حسابرسی."""
from __future__ import annotations

import time

from omid.core.permissions import RiskLevel
from omid.core.tools import Tool, ToolResult


def test_builtin_tools_registered(ctx):
    names = ctx.tools.names()
    expected = {
        "system_status", "get_branding", "describe_capabilities", "list_devices",
        "device_status", "discover_devices", "query_knowledge", "recall_memory",
        "remember_preference", "run_diagnostics", "simulate_motion", "trigger_estop",
        "physical_motion", "set_operation_mode",
    }
    assert expected.issubset(set(names))


def test_unknown_tool_refused_honestly(ctx):
    result = ctx.tools.invoke("rm_rf_everything", {}, ctx)
    assert result.ok is False
    assert "وجود ندارد" in (result.error or "")
    assert result.evidence["granted"] is False


def test_read_tool_works_in_observe(ctx):
    ctx.safety.request_mode("observe")
    result = ctx.tools.invoke("system_status", {}, ctx)
    assert result.ok is True
    assert result.data["safety"]["mode"] == "observe"


def test_simulate_tool_blocked_in_observe(ctx):
    ctx.safety.request_mode("observe")
    result = ctx.tools.invoke("simulate_motion", {"x": 10}, ctx)
    assert result.ok is False
    assert "مجاز نیست" in (result.error or "")


def test_physical_tool_needs_control_credentials(ctx):
    # حتی در حالت control (در صورت دستیابی)، بدون اعتبار کنترل رد می‌شود
    result = ctx.tools.invoke("physical_motion", {"x": 1}, ctx, control_granted=False)
    assert result.ok is False
    assert "اعتبار کنترل" in (result.error or "")


def test_disabled_tool_killswitch(ctx):
    ctx.policy.disable_tool("run_diagnostics")
    result = ctx.tools.invoke("run_diagnostics", {}, ctx)
    assert result.ok is False
    assert "غیرفعال" in (result.error or "")
    ctx.policy.enable_tool("run_diagnostics")
    assert ctx.tools.invoke("run_diagnostics", {}, ctx).ok is True


def test_tool_timeout(ctx):
    def slow_handler(args, c):
        time.sleep(2.0)
        return ToolResult(ok=True)

    ctx.tools.register(Tool(name="slow_tool", description="slow", risk=RiskLevel.READ,
                            handler=slow_handler, timeout_s=0.3))
    started = time.monotonic()
    result = ctx.tools.invoke("slow_tool", {}, ctx)
    elapsed = time.monotonic() - started
    assert result.ok is False
    assert "زمان‌خورده" in (result.error or "")
    assert elapsed < 1.5


def test_handler_exception_reported_not_raised(ctx):
    def bad_handler(args, c):
        raise RuntimeError("boom")

    ctx.tools.register(Tool(name="bad_tool", description="bad", risk=RiskLevel.READ, handler=bad_handler))
    result = ctx.tools.invoke("bad_tool", {}, ctx)
    assert result.ok is False
    assert "boom" in (result.error or "")


def test_invocations_are_audited(ctx):
    ctx.tools.invoke("system_status", {}, ctx, audit=ctx.audit_event)
    types = [e["type"] for e in ctx.bus.history(50)]
    assert "tool.invoked" in types
    assert "tool.completed" in types


def test_denial_is_audited(ctx):
    ctx.safety.request_mode("observe")
    ctx.tools.invoke("simulate_motion", {"x": 1}, ctx, audit=ctx.audit_event)
    types = [e["type"] for e in ctx.bus.history(50)]
    assert "tool.denied" in types


def test_evidence_attached(ctx):
    result = ctx.tools.invoke("system_status", {}, ctx)
    assert result.evidence["tool"] == "system_status"
    assert result.evidence["risk"] == "read"
    assert result.evidence["granted"] is True
    assert "elapsed_ms" in result.evidence


def test_audit_log_redacts_sensitive_values(ctx):
    ctx.audit_event("test.secret", "تست", data={"api_key": "TOPSECRET", "safe": "ok"})
    recent = ctx.audit_log.recent(20)
    joined = str(recent)
    assert "TOPSECRET" not in joined
    assert "REDACTED" in joined
