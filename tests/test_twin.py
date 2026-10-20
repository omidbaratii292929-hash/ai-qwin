"""آزمون Digital Twin — برچسب‌های صریح و عدم صدور فرمان فیزیکی."""
from __future__ import annotations

from omid.safety.validator import MotionCommand


def test_preview_motion_labeled_simulation(ctx):
    result = ctx.twin.preview_motion("grbl-01", MotionCommand(x=10, y=20, feed=300))
    assert result["ok"] is True
    assert result["source"] == "simulation"
    assert result["estimated_position"]["x"] == 10.0
    assert "شبیه‌سازی" in result["note"]


def test_preview_motion_rejects_out_of_range(ctx):
    result = ctx.twin.preview_motion("grbl-01", MotionCommand(x=99999))
    assert result["ok"] is False
    assert "محدوده" in result["error"]


def test_snapshot_label_and_no_live_without_hardware(ctx):
    ctx.twin.preview_motion("grbl-01", MotionCommand(x=5))
    snapshot = ctx.twin.snapshot()
    assert snapshot["label"] == "SIMULATION"
    assert snapshot["live"] is None  # بدون سخت‌افزار، وضعیت زنده جعل نمی‌شود
    assert any(t["device_id"] == "grbl-01" for t in snapshot["twins"])
    assert snapshot["safety_mode"] == ctx.safety.mode


def test_run_scenario_blocks_physical_steps(ctx):
    scenario = ctx.twin.run_scenario(
        [
            {"tool": "system_status", "args": {}},
            {"tool": "simulate_motion", "args": {"x": 30}},
            {"tool": "physical_motion", "args": {"x": 30}},  # باید صادقانه رد شود
        ]
    )
    assert scenario["label"] == "SIMULATION"
    assert scenario["steps_executed"] == 3
    assert scenario["transcript"][0]["ok"] is True
    assert scenario["transcript"][1]["ok"] is True
    physical = scenario["transcript"][2]
    assert physical["ok"] is False
    assert physical["error"]


def test_twin_state_is_isolated_per_device(ctx):
    ctx.twin.preview_motion("device-a", MotionCommand(x=11))
    ctx.twin.preview_motion("device-b", MotionCommand(x=22))
    assert ctx.twin.state("device-a").position["x"] == 11.0
    assert ctx.twin.state("device-b").position["x"] == 22.0
