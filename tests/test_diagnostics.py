"""آزمون تشخیص عیب — قواعد، رتبه‌بندی و برچسب صادقانهٔ منبع."""
from __future__ import annotations

from omid.diagnostics.rules import BUILTIN_RULES, FaultDetector, Rule


def test_builtin_rules_present():
    ids = {r.id for r in BUILTIN_RULES}
    assert {"temp-high", "temp-critical", "vibration-high", "comm-timeouts"} <= ids


def test_critical_ranked_first():
    detector = FaultDetector()
    findings = detector.check(
        "grbl-01",
        {"temperature_c": 95.0, "vibration_mm_s": 8.0, "spindle_load_pct": 90.0},
        source="live",
    )
    assert findings
    assert findings[0].severity == "critical"
    assert all(f.source == "live" for f in findings)


def test_healthy_metrics_no_findings():
    detector = FaultDetector()
    findings = detector.check(
        "grbl-01",
        {"temperature_c": 40.0, "vibration_mm_s": 1.0, "spindle_load_pct": 30.0, "comm_timeout_count": 0},
    )
    assert findings == []


def test_simulation_source_is_labeled():
    detector = FaultDetector()
    findings = detector.check("grbl-01", {"temperature_c": 95.0}, source="simulation")
    assert findings[0].source == "simulation"  # هرگز live وانمود نمی‌شود


def test_findings_have_suggestion_and_confidence():
    detector = FaultDetector()
    finding = detector.check("d", {"temperature_c": 80.0})[0]
    assert finding.suggestion
    assert 0.0 < finding.confidence <= 1.0


def test_custom_rule_extension():
    detector = FaultDetector(
        extra_rules=(
            Rule(
                id="coolant-low", metric="coolant_l", description="مخزن خنک‌کننده کم است",
                severity="warning", confidence=0.9, suggestion="مخزن را پر کنید.", min_value=2.0,
            ),
        )
    )
    findings = detector.check("d", {"coolant_l": 0.5})
    assert [f.rule_id for f in findings] == ["coolant-low"]


def test_scan_all_with_simulated_driver(ctx):
    report = ctx.diagnostics.scan_all(ctx)
    assert report["method"] == "rule-based"
    assert "پیش‌بینی" in report["disclaimer"]
    results = report["results"]
    assert any(r.get("driver") == "grbl" for r in results)
    grbl_result = next(r for r in results if r.get("driver") == "grbl")
    assert grbl_result["source"] == "simulation"  # متریک شبیه‌سازی برچسب دارد


def test_recent_findings_limit(ctx):
    detector = ctx.diagnostics
    for i in range(5):
        detector.check(f"d{i}", {"temperature_c": 100.0})
    findings = detector.recent_findings(limit=3)
    assert len(findings) <= 3 * 2  # هر اسکن می‌تواند دو قاعدهٔ دما را فعال کند
