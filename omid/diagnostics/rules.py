"""omid.diagnostics.rules — تشخیص عیب مبتنی بر قواعد فنی.

**صداقت دربارهٔ سطح قابلیت:** این ماژول «تحلیل قواعد-محور» است، نه مدل
پیش‌بینی تأییدشده. پیش‌بینی خرابی واقعی به دادهٔ عملیاتی و ارزیابی نیاز
دارد که هنوز جمع‌آوری نشده است؛ هر Finding دارای severity و confidence و
منبع داده (simulation/live) است و دادهٔ شبیه‌سازی‌شده هرگز به‌عنوان
اندازه‌گیری زنده گزارش نمی‌شود.

© هوشمندسازی صنعت امید — OMID Industrial AI Agent
طراح و سازندهٔ اصلی: مهندس امید براتی
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from omid.events import utc_now_iso

SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}


@dataclass(frozen=True)
class Rule:
    """قاعدهٔ تشخیص: مرز مجاز یک متریک + پیشنهاد اقدام."""

    id: str
    metric: str
    description: str
    severity: str  # warning | critical
    confidence: float
    suggestion: str
    max_value: float | None = None
    min_value: float | None = None

    def evaluate(self, value: float) -> bool:
        if self.max_value is not None and value > self.max_value:
            return True
        if self.min_value is not None and value < self.min_value:
            return True
        return False


@dataclass
class Finding:
    """یک یافتهٔ تشخیصی با رتبه‌بندی و دلیل."""

    rule_id: str
    device_id: str
    metric: str
    value: float
    severity: str
    confidence: float
    suggestion: str
    source: str  # simulation | live
    ts: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "device_id": self.device_id,
            "metric": self.metric,
            "value": self.value,
            "severity": self.severity,
            "confidence": self.confidence,
            "suggestion": self.suggestion,
            "source": self.source,
            "ts": self.ts,
        }


# قواعد داخلی مبتنی بر دانش فنی عمومی صنعتی (قابل توسعه توسط کاربر)
BUILTIN_RULES: tuple[Rule, ...] = (
    Rule(
        id="temp-high",
        metric="temperature_c",
        description="دمای تجهیز بیش از حد مجاز",
        severity="warning",
        confidence=0.7,
        suggestion="بار دستگاه را کاهش دهید و تهویه/خنک‌کاری را بررسی کنید.",
        max_value=75.0,
    ),
    Rule(
        id="temp-critical",
        metric="temperature_c",
        description="دمای بحرانی تجهیز",
        severity="critical",
        confidence=0.85,
        suggestion="توقف فوری عملیات و بررسی سیستم خنک‌کاری پیش از ادامه.",
        max_value=90.0,
    ),
    Rule(
        id="vibration-high",
        metric="vibration_mm_s",
        description="لرزش بالاتر از حد مجاز (مرزهای عمومی ISO 10816)",
        severity="warning",
        confidence=0.6,
        suggestion="اتصالات مکانیکی، بالانس و پایهٔ دستگاه بررسی شود.",
        max_value=4.5,
    ),
    Rule(
        id="vibration-critical",
        metric="vibration_mm_s",
        description="لرزش بحرانی",
        severity="critical",
        confidence=0.75,
        suggestion="توقف دستگاه؛ احتمال خرابی بلبرینگ یا ناهمرازی شدید.",
        max_value=7.1,
    ),
    Rule(
        id="spindle-overload",
        metric="spindle_load_pct",
        description="بار اسپیندل بیش از حد",
        severity="warning",
        confidence=0.65,
        suggestion="عمق/نرخ برش کاهش یابد؛ ابزار از نظر فرسودگی بررسی شود.",
        max_value=85.0,
    ),
    Rule(
        id="comm-timeouts",
        metric="comm_timeout_count",
        description="تکرار timeout ارتباطی با تجهیز",
        severity="warning",
        confidence=0.7,
        suggestion="کابل/اتصال و نویز محیطی بررسی شود؛ در تداوم، ارتباط قطع و بازرسی شود.",
        max_value=3.0,
    ),
    Rule(
        id="comm-timeouts-critical",
        metric="comm_timeout_count",
        description="قطعی پایدار ارتباط با تجهیز",
        severity="critical",
        confidence=0.85,
        suggestion="توقف عملیات خودکار؛ ارتباط تا بازرسی کامل فیزیکی برقرار نشود.",
        max_value=10.0,
    ),
)


class FaultDetector:
    """موتور تشخیص عیب قواعد-محور با رتبه‌بندی شدت و اطمینان."""

    def __init__(self, extra_rules: tuple[Rule, ...] = ()) -> None:
        self._rules: list[Rule] = list(BUILTIN_RULES) + list(extra_rules)
        self._findings: list[Finding] = []
        self._lock = threading.RLock()

    @property
    def rules(self) -> list[Rule]:
        return list(self._rules)

    def add_rule(self, rule: Rule) -> None:
        with self._lock:
            self._rules.append(rule)

    def check(self, device_id: str, metrics: dict[str, Any], *, source: str = "live") -> list[Finding]:
        """بررسی یک مجموعه متریک برای یک دستگاه؛ source برچسب صادقانهٔ داده است."""
        found: list[Finding] = []
        for rule in self._rules:
            value = metrics.get(rule.metric)
            if value is None:
                continue
            try:
                value_f = float(value)
            except (TypeError, ValueError):
                continue
            if rule.evaluate(value_f):
                found.append(
                    Finding(
                        rule_id=rule.id,
                        device_id=device_id,
                        metric=rule.metric,
                        value=value_f,
                        severity=rule.severity,
                        confidence=rule.confidence,
                        suggestion=rule.suggestion,
                        source=source,
                    )
                )
        # رتبه‌بندی: شدت بالاتر، سپس اطمینان بالاتر
        found.sort(key=lambda f: (SEVERITY_ORDER.get(f.severity, 0), f.confidence), reverse=True)
        with self._lock:
            self._findings.extend(found)
            self._findings = self._findings[-500:]
        return found

    def recent_findings(self, limit: int = 50, *, device_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            findings = list(self._findings)
        if device_id:
            findings = [f for f in findings if f.device_id == device_id]
        return [f.to_dict() for f in findings[-limit:]]

    def scan_all(self, ctx: Any) -> dict[str, Any]:
        """اسکن همهٔ دستگاه‌های دارای درایور؛ منبع داده صادقانه برچسب می‌خورد."""
        results: list[dict[str, Any]] = []
        for name, driver in getattr(ctx, "drivers", {}).items():
            metrics_fn = getattr(driver, "simulated_metrics", None)
            if metrics_fn is None:
                results.append({"driver": name, "ok": False, "reason": "درایور متریک قابل‌بررسی ارائه نمی‌دهد."})
                continue
            metrics = metrics_fn()
            source = metrics.pop("source", "simulation")
            findings = self.check(getattr(driver, "device_id", name), metrics, source=source)
            results.append(
                {
                    "driver": name,
                    "device_id": getattr(driver, "device_id", name),
                    "source": source,
                    "metrics": metrics,
                    "findings": [f.to_dict() for f in findings],
                }
            )
        return {
            "scanned_at": utc_now_iso(),
            "method": "rule-based",
            "disclaimer": "تحلیل قواعد-محور است، نه مدل پیش‌بینی تأییدشده؛ دادهٔ simulation اندازه‌گیری زنده نیست.",
            "results": results,
        }
