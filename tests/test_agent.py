"""آزمون هستهٔ عامل — برنامه‌ریزی قواعد-محور و LLM، تفکیک تصمیم از اجرا."""
from __future__ import annotations

import json

from omid.ai.ollama import HealthStatus, ProviderResult
from omid.core.tasks import Step, TaskStatus


# ---------- موتور قواعد-محور ----------
def test_persian_status_request(ctx):
    task = ctx.agent.handle_request("وضعیت سیستم را بررسی کن")
    assert task.status == TaskStatus.COMPLETED.value
    assert task.steps[0].tool == "system_status"
    assert task.planner.startswith("rule-based")
    assert task.result_summary


def test_english_status_request(ctx):
    task = ctx.agent.handle_request("show me system health status")
    assert task.status == TaskStatus.COMPLETED.value
    assert task.steps[0].tool == "system_status"


def test_devices_request(ctx):
    task = ctx.agent.handle_request("لیست تجهیزات را نشان بده")
    assert task.steps[0].tool == "list_devices"
    assert task.status == TaskStatus.COMPLETED.value


def test_branding_request(ctx):
    task = ctx.agent.handle_request("درباره پروژه چه کسی سازنده است؟")
    assert task.steps[0].tool == "get_branding"
    assert task.steps[0].result["company_name"] == "هوشمندسازی صنعت امید"


def test_help_request(ctx):
    task = ctx.agent.handle_request("کمک")
    assert task.steps[0].tool == "describe_capabilities"
    assert task.status == TaskStatus.COMPLETED.value


def test_unknown_intent_is_honest(ctx):
    task = ctx.agent.handle_request("آسمان آبی است و پرنده پرواز می‌کند")
    assert task.status == TaskStatus.COMPLETED.value
    assert task.steps[0].tool == "describe_capabilities"


def test_empty_request_fails_honestly(ctx):
    task = ctx.agent.handle_request("   ")
    assert task.status == TaskStatus.FAILED.value
    assert task.error


def test_simulate_motion_via_agent_updates_twin(ctx):
    task = ctx.agent.handle_request("حرکت به x=100 y=50 z=-5 با feed=800 را شبیه‌سازی کن")
    assert task.steps[0].tool == "simulate_motion"
    assert task.status == TaskStatus.COMPLETED.value
    twin = ctx.twin.state(ctx.grbl.device_id)
    assert twin.position == {"x": 100.0, "y": 50.0, "z": -5.0}
    assert twin.source == "simulation"


def test_simulate_motion_out_of_limits_fails(ctx):
    task = ctx.agent.handle_request("شبیه‌سازی حرکت x=99999")
    assert task.status == TaskStatus.FAILED.value
    assert "محدوده" in (task.error or "")


def test_estop_via_agent_blocks_motion(ctx):
    task = ctx.agent.handle_request("توقف اضطراری را فعال کن")
    assert task.status == TaskStatus.COMPLETED.value
    assert ctx.safety.estop_active is True
    motion = ctx.agent.handle_request("شبیه‌سازی حرکت x=10")
    assert motion.status == TaskStatus.FAILED.value


def test_completed_task_recorded_in_memory(ctx):
    ctx.agent.handle_request("وضعیت")
    ops = ctx.memory.list_operations(limit=5)
    assert any(o["goal"] == "وضعیت" for o in ops)


# ---------- مسیر LLM (با ارائه‌دهندهٔ ساختگی) ----------
class FakeAI:
    def __init__(self, reply: str):
        self.reply = reply
        self.calls = 0

    def health(self):
        return HealthStatus(True, ["fake-model:latest"], 1.0, None)

    def chat(self, messages, **kwargs):
        self.calls += 1
        return ProviderResult(ok=True, text=self.reply)

    def close(self):
        pass


def make_llm_ctx(tmp_path, monkeypatch, reply):
    monkeypatch.setenv("OMID_DATA_DIR", str(tmp_path / "llm"))
    monkeypatch.setenv("OMID_OLLAMA_MODEL", "fake-model")
    monkeypatch.setenv("OMID_OLLAMA_URL", "http://127.0.0.1:9")
    from omid.config import OMIDConfig
    from omid.context import AppContext

    ctx = AppContext(OMIDConfig.from_env())
    ctx.ai = FakeAI(reply)
    ctx.ai_health(force=True)
    return ctx


def test_llm_plan_executed(tmp_path, monkeypatch):
    reply = json.dumps({"steps": [{"tool": "system_status", "args": {}}]})
    ctx = make_llm_ctx(tmp_path, monkeypatch, reply)
    try:
        task = ctx.agent.handle_request("بررسی سلامت سامانه")
        assert task.planner == "llm"
        assert task.status == TaskStatus.COMPLETED.value
    finally:
        ctx.close()


def test_llm_invented_tool_is_rejected_and_falls_back(tmp_path, monkeypatch):
    # مدل سعی می‌کند ابزار ساختگی و حذف‌کننده فراخوانی کند → باید رد شود
    reply = json.dumps({"steps": [{"tool": "delete_all_files", "args": {"path": "/"}}]})
    ctx = make_llm_ctx(tmp_path, monkeypatch, reply)
    try:
        task = ctx.agent.handle_request("وضعیت سیستم")
        assert task.planner.startswith("rule-based")  # fallback صادقانه
        assert task.steps[0].tool == "system_status"
        types = [e["type"] for e in ctx.bus.history(50)]
        assert "agent.llm_invalid_plan" in types
    finally:
        ctx.close()


def test_llm_raw_gcode_never_executed(tmp_path, monkeypatch):
    reply = "Sure! Run this: G1 X50 Y50 F1000 and also `rm -rf /`"
    ctx = make_llm_ctx(tmp_path, monkeypatch, reply)
    try:
        task = ctx.agent.handle_request("move the laser now")
        # خروجی متنی آزاد LLM هرگز اجرا نمی‌شود؛ JSON معتبر نیست → fallback
        assert task.planner.startswith("rule-based")
        assert all("rm" not in json.dumps(s.to_dict()) for s in task.steps)
    finally:
        ctx.close()


def test_llm_markdown_wrapped_json_tolerated(tmp_path, monkeypatch):
    reply = "```json\n{\"steps\": [{\"tool\": \"get_branding\", \"args\": {}}]}\n```"
    ctx = make_llm_ctx(tmp_path, monkeypatch, reply)
    try:
        task = ctx.agent.handle_request("about the project")
        assert task.planner == "llm"
        assert task.steps[0].tool == "get_branding"
    finally:
        ctx.close()


# ---------- تأیید صریح عملیات فیزیکی ----------
def test_physical_step_waits_for_confirmation(tmp_path, monkeypatch):
    monkeypatch.setenv("OMID_MODE", "control")
    monkeypatch.setenv("OMID_ALLOW_PHYSICAL_CONTROL", "1")
    monkeypatch.setenv("OMID_DATA_DIR", str(tmp_path / "phys"))
    monkeypatch.setenv("OMID_OLLAMA_URL", "http://127.0.0.1:9")
    from omid.config import OMIDConfig
    from omid.context import AppContext

    ctx = AppContext(OMIDConfig.from_env())
    try:
        assert ctx.safety.mode == "control"

        task = ctx.tasks.create(goal="physical move", requested_by="test")
        task.steps = [Step(tool="physical_motion", args={"x": 10})]
        ctx.agent._execute(task, start_index=0, control_granted=True, timeout_s=10)
        assert task.status == TaskStatus.WAITING_CONFIRM.value
        assert task.steps[0].status == "awaiting_confirm"

        # تأیید صریح → ادامهٔ اجرا؛ بدون سخت‌افزار صادقانه رد می‌شود (جعل موفقیت نمی‌شود)
        confirmed = ctx.agent.confirm_task(task.id, control_granted=True)
        assert confirmed is not None
        assert confirmed.status == TaskStatus.FAILED.value
        assert "سخت‌افزار" in (confirmed.error or "") or "connected" in (confirmed.error or "")
        types = [e["type"] for e in ctx.bus.history(100)]
        assert "agent.confirm_required" in types
        assert "agent.confirmed" in types
    finally:
        ctx.close()


def test_physical_step_denied_without_control_credentials(ctx):

    task = ctx.tasks.create(goal="sneaky", requested_by="test")
    task.steps = [Step(tool="physical_motion", args={"x": 1})]
    ctx.agent._execute(task, start_index=0, control_granted=False, timeout_s=5)
    assert task.status == TaskStatus.FAILED.value
    assert "اعتبار کنترل" in (task.error or "")


def test_cancel_finished_task_returns_false(ctx):
    task = ctx.agent.handle_request("وضعیت")
    assert ctx.tasks.request_cancel(task.id) is False


def test_cancel_pending_task_flag(ctx):
    task = ctx.tasks.create(goal="manual", requested_by="test")
    task.status = TaskStatus.RUNNING.value
    assert ctx.tasks.request_cancel(task.id) is True
    assert task.cancel_requested is True
