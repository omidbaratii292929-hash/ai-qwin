"""omid.context — ریشهٔ ترکیب (Composition Root) سامانه OMID.

همهٔ اجزا اینجا ساخته و به‌هم متصل می‌شوند: پیکربندی، گذرگاه رویداد،
لاگ حسابرسی، مدیر ایمنی، رجیستری دستگاه‌ها، درایورها، twin، پایگاه دانش،
حافظه، تشخیص عیب، ارائه‌دهندهٔ AI، رجیستری ابزارها، مدیر وظایف و عامل.
API، CLI و آزمون‌ها همه از همین ریشه استفاده می‌کنند تا رفتار یکسان بماند.

© هوشمندسازی صنعت امید — OMID Industrial AI Agent
طراح و سازندهٔ اصلی: مهندس امید براتی
با همکاری: دکتر کیمیا زهرا براتی و مهندس محسن بابایی
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from omid import __version__, branding
from omid.ai.ollama import HealthStatus, OllamaProvider
from omid.config import OMIDConfig
from omid.core.agent import AgentRuntime
from omid.core.builtin_tools import register_builtin_tools
from omid.core.permissions import PermissionPolicy
from omid.core.tasks import TaskManager
from omid.core.tools import ToolRegistry
from omid.diagnostics.rules import FaultDetector
from omid.discovery.registry import DeviceRegistry, discover_network, discover_serial
from omid.drivers.grbl import GRBLDriver
from omid.events import AUDITED_SEVERITIES, AuditLog, Event, EventBus
from omid.knowledge.rag import KnowledgeBase
from omid.memory.store import MemoryStore
from omid.safety.modes import SafetyManager
from omid.twin.simulator import DigitalTwin


class AppContext:
    """ظرف مرکزی وابستگی‌ها و سرویس‌های سامانه."""

    def __init__(self, config: OMIDConfig | None = None) -> None:
        self.config = config or OMIDConfig.from_env()
        self.started_at = time.time()

        self.data_dir = Path(self.config.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # رویدادها و حسابرسی
        self.bus = EventBus()
        self.audit_log = AuditLog(self.data_dir / "audit.jsonl")
        self.bus.subscribe(
            lambda ev: self.audit_log.append(ev) if ev.severity in AUDITED_SEVERITIES else None
        )

        # ایمنی — پیش از هر چیز دیگر
        self.safety = SafetyManager(
            requested_mode=self.config.mode,
            allow_physical_control=self.config.allow_physical_control,
            audit=self.audit_event,
        )

        # تجهیزات و درایورها
        self.devices = DeviceRegistry(self.data_dir / "devices.json")
        self.grbl = GRBLDriver(
            device_id="grbl-01",
            limits=self.config.limits,
            backend="simulated",  # پیش‌فرض امن؛ backend سریال فقط با پیکربندی صریح روی ماشین مجاز
            safety=self.safety,
            audit=self.audit_event,
        )
        self.drivers: dict[str, Any] = {"grbl": self.grbl}

        # twin و هوشمندی
        self.twin = DigitalTwin(self)
        self.knowledge = KnowledgeBase(self.data_dir)
        self.memory = MemoryStore(self.data_dir / "memory.sqlite3")
        self.diagnostics = FaultDetector()

        # AI محلی (اختیاری)
        self.ai = OllamaProvider(self.config.ollama_url, self.config.ollama_model, self.config.ollama_timeout)
        self._ai_health: HealthStatus | None = None
        self._ai_health_at = 0.0

        # هستهٔ عامل
        self.policy = PermissionPolicy(self.safety)
        self.tools = ToolRegistry(self.policy)
        self.tasks = TaskManager()
        register_builtin_tools(self)
        self.agent = AgentRuntime(self)

        self.audit_event(
            "system.startup",
            f"OMID Industrial AI Agent v{__version__} آغاز به کار کرد — حالت: {self.safety.mode}.",
            data={"version": __version__, "mode": self.safety.mode},
            severity="audit",
        )

    # ---------- حسابرسی ----------
    def audit_event(
        self,
        type_: str,
        message: str,
        data: dict[str, Any] | None = None,
        severity: str = "audit",
        source: str = "omid",
    ) -> Event:
        event = Event(type=type_, message=message, severity=severity, source=source, data=data or {})
        self.bus.publish(event)
        return event

    # ---------- سلامت AI با کش ----------
    def ai_health(self, *, max_age_s: float = 30.0, force: bool = False) -> HealthStatus:
        now = time.monotonic()
        if not force and self._ai_health is not None and (now - self._ai_health_at) < max_age_s:
            return self._ai_health
        self._ai_health = self.ai.health()
        self._ai_health_at = now
        return self._ai_health

    def ai_available(self) -> bool:
        """AI فقط وقتی «در دسترس» است که سرویس سالم و مدل پیکربندی شده باشد."""
        health = self.ai_health()
        return bool(health.available and self.config.ollama_model)

    # ---------- کشف ----------
    def discover_serial(self) -> dict[str, Any]:
        return discover_serial(self.devices, audit=self.audit_event)

    def discover_network(self) -> dict[str, Any]:
        return discover_network(
            self.devices,
            allowlist=self.config.network_allowlist,
            ports=self.config.network_probe_ports,
            audit=self.audit_event,
        )

    # ---------- وضعیت و خودآزمایی ----------
    def status(self) -> dict[str, Any]:
        health = self.ai_health()
        return {
            "project": branding.get("project_name"),
            "version": __version__,
            "uptime_s": round(time.time() - self.started_at, 1),
            "safety": self.safety.snapshot(),
            "ai": {
                "configured": bool(self.config.ollama_model),
                "model": self.config.ollama_model or None,
                **health.to_dict(),
            },
            "devices_count": self.devices.count(),
            "knowledge_docs": self.knowledge.count(),
            "memory": self.memory.stats(),
            "tools": len(self.tools.names()),
            "recent_findings": len(self.diagnostics.recent_findings(limit=100)),
        }

    def selfcheck(self) -> dict[str, Any]:
        """خودآزمایی کامل با شواهد — برای CLI، CI و گزارش‌ها."""
        checks: dict[str, Any] = {}
        try:
            brand = branding.load_branding(refresh=True)
            checks["branding"] = {"ok": True, "detail": brand["company_name"]}
        except Exception as exc:  # noqa: BLE001
            checks["branding"] = {"ok": False, "detail": str(exc)}
        checks["config"] = {"ok": True, "detail": self.config.public_view()}
        checks["safety"] = {"ok": not self.safety.estop_active, "detail": self.safety.snapshot()}
        checks["tools"] = {"ok": len(self.tools.names()) >= 10, "detail": self.tools.names()}
        try:
            probe_key = "__selfcheck__"
            self.memory.set_preference(probe_key, "ok")
            prefs = self.memory.get_preferences()
            ok = prefs.get(probe_key, {}).get("value") == "ok"
            self.memory.delete_preference(probe_key)
            checks["memory"] = {"ok": ok, "detail": self.memory.stats()}
        except Exception as exc:  # noqa: BLE001
            checks["memory"] = {"ok": False, "detail": str(exc)}
        checks["knowledge"] = {"ok": True, "detail": {"docs": self.knowledge.count()}}
        health = self.ai_health(force=True)
        checks["ai_ollama"] = {
            "ok": True,  # نبودِ Ollama خطا نیست؛ قابلیت اختیاری است — اما صادقانه گزارش می‌شود
            "available": health.available,
            "detail": health.to_dict(),
        }
        try:
            import serial  # type: ignore  # noqa: F401

            serial_available = True
        except ImportError:
            serial_available = False
        checks["serial_support"] = {
            "ok": True,
            "available": serial_available,
            "detail": "pyserial نصب است" if serial_available else "pyserial نصب نیست — کشف/کنترل سریال واقعی در دسترس نیست (صادقانه)",
        }
        checks["audit_log"] = {"ok": True, "detail": str(self.audit_log.path)}
        overall = all(c.get("ok", False) for c in checks.values())
        return {
            "overall_ok": overall,
            "project": branding.get("project_name"),
            "version": __version__,
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "checks": checks,
        }

    # ---------- پایان ----------
    def close(self) -> None:
        try:
            self.memory.close()
        except Exception:  # noqa: BLE001
            pass
        self.ai.close()
