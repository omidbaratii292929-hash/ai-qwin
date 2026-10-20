"""omid.discovery — کشف کنترل‌شدهٔ تجهیزات و رجیستری دستگاه‌ها.

اصول:
- کشف خودکار به معنی امکان کنترل نیست؛ دستگاه ناشناخته صادقانه
  ``unsupported`` گزارش می‌شود.
- اسکن شبکه **فقط** روی فهرست مجاز (allowlist) پیکربندی‌شده و با probe
  محدود TCP انجام می‌شود؛ بدون allowlist هیچ اسکنی صورت نمی‌گیرد
  (جلوگیری از اسکن تهاجمی).
- اگر pyserial نصب نباشد، کشف سریال به‌جای وانمود کردن، «در دسترس نبودن»
  را صادقانه گزارش می‌کند.

© هوشمندسازی صنعت امید — OMID Industrial AI Agent
طراح و سازندهٔ اصلی: مهندس امید براتی
"""
from __future__ import annotations

import json
import socket
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from omid.events import utc_now_iso

# حدس پروتکل از پورت (فرض قطعی نیست — confidence پایین ثبت می‌شود)
PORT_PROTOCOL_GUESS = {502: "modbus-tcp", 4840: "opc-ua", 1883: "mqtt", 80: "http", 443: "https"}


@dataclass
class Device:
    """رکورد یک دستگاه شناخته‌شده با سطح اطمینان تشخیص."""

    id: str
    kind: str  # serial | network | camera | unknown
    interface: str
    protocol: str = "unknown"
    vendor: str | None = None
    model: str | None = None
    status: str = "detected"  # detected | connected | offline | unsupported
    last_seen: str = field(default_factory=utc_now_iso)
    capabilities: list[str] = field(default_factory=list)
    confidence: float = 0.5
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DeviceRegistry:
    """رجیستری پایدار دستگاه‌ها (JSON روی دیسک)."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._devices: dict[str, Device] = {}
        self._lock = threading.RLock()
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for item in raw.get("devices", []):
                dev = Device(**{k: v for k, v in item.items() if k in Device.__dataclass_fields__})
                self._devices[dev.id] = dev
        except (OSError, json.JSONDecodeError, TypeError):
            pass  # فایل خراب → با رجیستری خالی شروع می‌کنیم (بدون crash)

    def _persist(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"updated_at": utc_now_iso(), "devices": [d.to_dict() for d in self._devices.values()]}
            self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def upsert(self, device: Device) -> None:
        with self._lock:
            device.last_seen = utc_now_iso()
            self._devices[device.id] = device
            self._persist()

    def get(self, device_id: str) -> Device | None:
        with self._lock:
            return self._devices.get(device_id)

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [d.to_dict() for d in self._devices.values()]

    def remove(self, device_id: str) -> bool:
        with self._lock:
            existed = self._devices.pop(device_id, None) is not None
            if existed:
                self._persist()
            return existed

    def count(self) -> int:
        with self._lock:
            return len(self._devices)


def discover_serial(registry: DeviceRegistry, audit: Callable[..., None] | None = None) -> dict[str, Any]:
    """کشف پورت‌های سریال/USB — با import محافظت‌شده و گزارش صادقانه."""
    audit = audit or (lambda *a, **k: None)
    try:
        from serial.tools import list_ports  # type: ignore
    except ImportError:
        audit(
            "discovery.serial_unavailable",
            "pyserial نصب نیست؛ کشف سریال در دسترس نیست (صادقانه گزارش شد، چیزی وانمود نشد).",
            severity="info",
        )
        return {
            "available": False,
            "reason": "pyserial نصب نیست. برای کشف پورت سریال: pip install pyserial",
            "found": [],
        }
    found: list[dict[str, Any]] = []
    for port in list_ports.comports():
        device_id = port.device or f"serial-{len(found)}"
        dev = Device(
            id=device_id,
            kind="serial",
            interface=device_id,
            protocol="usb-serial",
            vendor=getattr(port, "manufacturer", None),
            model=getattr(port, "product", None) or getattr(port, "description", None),
            status="detected",
            capabilities=["status-read"],
            confidence=0.6,
            notes="شناسایی از فهرست پورت‌های سیستم؛ پروتکل سطح بالا (مثل GRBL) هنوز تأیید نشده است.",
        )
        registry.upsert(dev)
        found.append(dev.to_dict())
    audit("discovery.serial", f"کشف سریال انجام شد: {len(found)} پورت.", data={"count": len(found)})
    return {"available": True, "found": found}


def discover_network(
    registry: DeviceRegistry,
    *,
    allowlist: tuple[str, ...],
    ports: tuple[int, ...] = (502, 4840, 1883),
    timeout_s: float = 0.4,
    audit: Callable[..., None] | None = None,
) -> dict[str, Any]:
    """probe محدود TCP فقط روی میزبان‌های مجازِ پیکربندی‌شده.

    بدون allowlist هیچ اسکنی انجام نمی‌شود (سیاست صریح ضد اسکن تهاجمی).
    باز بودن پورت به معنی تأیید پروتکل نیست → confidence پایین و note صادقانه.
    """
    audit = audit or (lambda *a, **k: None)
    if not allowlist:
        audit(
            "discovery.network_disabled",
            "کشف شبکه غیرفعال است: فهرست میزبان‌های مجاز (OMID_NETWORK_ALLOWLIST) خالی است.",
            severity="info",
        )
        return {
            "available": False,
            "reason": "اسکن شبکه بدون allowlist صریح طبق سیاست ایمنی غیرفعال است.",
            "found": [],
        }
    found: list[dict[str, Any]] = []
    for host in allowlist:
        for port in ports:
            reachable = False
            try:
                with socket.create_connection((host, port), timeout=timeout_s):
                    reachable = True
            except OSError:
                reachable = False
            if not reachable:
                continue
            device_id = f"{host}:{port}"
            dev = Device(
                id=device_id,
                kind="network",
                interface=f"tcp://{device_id}",
                protocol=PORT_PROTOCOL_GUESS.get(port, "unknown"),
                status="detected",
                capabilities=["tcp-reachable"],
                confidence=0.4,
                notes="فقط باز بودن پورت تأیید شده؛ پروتکل از روی شماره پورت حدس زده شده و تأیید نیست.",
            )
            registry.upsert(dev)
            found.append(dev.to_dict())
    audit("discovery.network", f"probe محدود شبکه: {len(found)} سرویس در دسترس.", data={"count": len(found)})
    return {"available": True, "hosts_probed": list(allowlist), "ports_probed": list(ports), "found": found}
