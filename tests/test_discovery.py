"""آزمون کشف تجهیزات و رجیستری دستگاه‌ها — صداقت در نبود قابلیت."""
from __future__ import annotations

from omid.discovery.registry import Device, DeviceRegistry, discover_network, discover_serial


def test_serial_discovery_is_honest(tmp_path):
    registry = DeviceRegistry(tmp_path / "devices.json")
    report = discover_serial(registry)
    assert "available" in report
    try:
        import serial  # type: ignore  # noqa: F401
        serial_installed = True
    except ImportError:
        serial_installed = False
    if serial_installed:
        assert report["available"] is True
    else:
        assert report["available"] is False
        assert "pyserial" in report["reason"]  # وانمود نمی‌کند، دلیل می‌دهد


def test_network_discovery_disabled_without_allowlist(tmp_path):
    registry = DeviceRegistry(tmp_path / "devices.json")
    report = discover_network(registry, allowlist=())
    assert report["available"] is False
    assert "allowlist" in report["reason"] or "سیاست" in report["reason"]
    assert registry.count() == 0


def test_network_probe_of_closed_port_is_safe(tmp_path):
    registry = DeviceRegistry(tmp_path / "devices.json")
    # پورت 9 روی loopback عملاً بسته است → بدون crash و بدون ثبت دستگاه
    report = discover_network(registry, allowlist=("127.0.0.1",), ports=(9,), timeout_s=0.2)
    assert report["available"] is True
    assert report["found"] == []


def test_registry_persistence_roundtrip(tmp_path):
    path = tmp_path / "devices.json"
    registry = DeviceRegistry(path)
    registry.upsert(Device(id="dev-1", kind="serial", interface="/dev/ttyUSB0", protocol="grbl", confidence=0.8))
    assert registry.count() == 1

    reloaded = DeviceRegistry(path)
    device = reloaded.get("dev-1")
    assert device is not None
    assert device.protocol == "grbl"
    assert device.confidence == 0.8

    assert reloaded.remove("dev-1") is True
    assert reloaded.count() == 0
    assert DeviceRegistry(path).count() == 0


def test_corrupt_registry_file_does_not_crash(tmp_path):
    path = tmp_path / "devices.json"
    path.write_text("{not json!!", encoding="utf-8")
    registry = DeviceRegistry(path)
    assert registry.count() == 0


def test_discovered_device_carries_confidence_and_notes(tmp_path):
    registry = DeviceRegistry(tmp_path / "devices.json")
    registry.upsert(
        Device(
            id="tcp-host:502", kind="network", interface="tcp://host:502",
            protocol="modbus-tcp", status="detected", confidence=0.4,
            notes="فقط باز بودن پورت تأیید شده است.",
        )
    )
    device = registry.get("tcp-host:502")
    assert device is not None
    assert 0.0 <= device.confidence <= 1.0
    assert device.notes  # تشخیص قطعی وانمود نمی‌شود
