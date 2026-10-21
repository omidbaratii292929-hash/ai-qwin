"""آزمون درایور GRBL — شبیه‌سازی، صداقت دربارهٔ نبود سخت‌افزار، توقف اضطراری."""
from __future__ import annotations

from omid.config import MachineLimits
from omid.drivers.grbl import GRBLDriver
from omid.safety.modes import CONTROL_CONFIRM_PHRASE, SafetyManager
from omid.safety.validator import MotionCommand


def make_driver(safety: SafetyManager) -> GRBLDriver:
    return GRBLDriver(device_id="grbl-test", limits=MachineLimits(), backend="simulated", safety=safety)


def test_capabilities_announce_simulation():
    driver = make_driver(SafetyManager(requested_mode="simulate"))
    caps = driver.capabilities()
    assert "simulation" in caps
    assert "status-read" in caps


def test_connect_and_status_are_simulated():
    driver = make_driver(SafetyManager(requested_mode="simulate"))
    result = driver.connect()
    assert result.ok is True
    assert result.source == "simulation"
    status = driver.read_status()
    assert status.ok is True
    assert status.source == "simulation"
    assert status.data["backend"] == "simulated"


def test_motion_in_simulate_mode_updates_sim_position():
    safety = SafetyManager(requested_mode="simulate")
    driver = make_driver(safety)
    driver.connect()
    result = driver.execute(MotionCommand(x=50, y=25, feed=400))
    assert result.ok is True
    assert result.source == "simulation"
    status = driver.read_status()
    assert status.data["position"]["x"] == 50.0
    assert status.data["position"]["y"] == 25.0


def test_motion_beyond_limits_rejected():
    driver = make_driver(SafetyManager(requested_mode="simulate"))
    result = driver.execute(MotionCommand(x=99999))
    assert result.ok is False
    assert "محدوده" in (result.error or "")


def test_raw_motion_gcode_never_sent():
    driver = make_driver(SafetyManager(requested_mode="simulate"))
    result = driver.execute("G1 X10 Y10 F1000")
    assert result.ok is False
    assert "خام" in (result.error or "")


def test_readonly_gcode_allowed_in_sim():
    driver = make_driver(SafetyManager(requested_mode="simulate"))
    result = driver.execute("?")
    assert result.ok is True
    assert result.source == "simulation"
    assert "simulated" in str(result.data["response"])


def test_estop_sets_alarm_and_blocks_motion():
    safety = SafetyManager(requested_mode="simulate")
    driver = make_driver(safety)
    estop = driver.estop("test halt")
    assert estop.ok is True
    status = driver.read_status()
    assert status.data["status"] == "Alarm"
    assert status.data["alarm"] == "test halt"
    safety.trigger_estop("test halt")
    blocked = driver.execute(MotionCommand(x=10))
    assert blocked.ok is False
    assert "توقف اضطراری" in (blocked.error or "")


def test_control_mode_without_hardware_refuses_honestly():
    """اجرای زنده بدون سخت‌افزار واقعی هرگز جعل نمی‌شود."""
    safety = SafetyManager(requested_mode="simulate", allow_physical_control=True)
    driver = make_driver(safety)
    safety.request_mode("control", confirm=CONTROL_CONFIRM_PHRASE)
    result = driver.execute(MotionCommand(x=10))
    assert result.ok is False
    assert "سخت‌افزار" in (result.error or "")
    assert result.source == "live"  # تلاش برای اجرای زنده بوده، نه شبیه‌سازی


def test_serial_backend_without_pyserial_is_honest():
    driver = GRBLDriver(device_id="grbl-ser", backend="serial", serial_port="/dev/ttyFAKE",
                        safety=SafetyManager(requested_mode="control", allow_physical_control=True))
    try:
        import serial  # type: ignore  # noqa: F401
        installed = True
    except ImportError:
        installed = False
    result = driver.connect()
    if not installed:
        assert result.ok is False
        assert "pyserial" in (result.error or "")
    else:
        # پورت جعلی → خطای اتصال صادقانه
        assert result.ok is False


def test_simulated_metrics_labeled():
    driver = make_driver(SafetyManager(requested_mode="simulate"))
    metrics = driver.simulated_metrics()
    assert metrics["source"] == "simulation"
    assert "temperature_c" in metrics


def test_clear_alarm_live_backend_fails_honestly():
    driver = GRBLDriver(backend="serial", serial_port="COM_TEST")
    result = driver.clear_alarm()
    assert result.ok is False
    assert result.source == "live"
    assert result.data["status"] == "unknown"
    assert "پیاده‌سازی نشده" in (result.error or "")
