"""Regression tests for truthful serial backend behavior; no physical hardware is used."""
from __future__ import annotations

from unittest.mock import MagicMock

from omid.drivers.grbl import GRBLDriver
from omid.safety.validator import MotionCommand


def make_driver():
    driver = GRBLDriver(backend="serial", serial_port="COM_TEST")
    return driver


def test_read_status_without_serial_does_not_fall_back_to_simulation():
    result = make_driver().read_status()
    assert result.ok is False
    assert result.source == "live"
    assert result.data is None or result.data.get("backend") != "simulated"


def test_readonly_command_without_serial_does_not_fake_success():
    result = make_driver().execute("$I")
    assert result.ok is False
    assert result.source == "live"


def test_estop_without_serial_does_not_claim_physical_stop():
    result = make_driver().estop("test")
    assert result.ok is False
    assert result.source == "live"
    assert result.data["physical_stop_confirmed"] is False


def test_estop_fails_if_either_serial_write_fails():
    driver = make_driver()
    driver._serial = MagicMock()
    driver._send_raw = MagicMock(side_effect=[None, "ok"])
    result = driver.estop("test")
    assert result.ok is False
    assert result.source == "live"
    assert result.data["physical_stop_confirmed"] is False


def test_estop_only_reports_io_confirmed_when_both_writes_succeed():
    driver = make_driver()
    driver._serial = MagicMock()
    driver._send_raw = MagicMock(side_effect=["ok", "ok"])
    result = driver.estop("test")
    assert result.ok is True
    assert result.source == "live"
    assert result.data["physical_stop_confirmed"] is False
    assert result.data["stop_commands_sent"] is True


def test_simulated_backend_still_returns_simulation_source():
    driver = GRBLDriver(backend="simulated")
    assert driver.connect().source == "simulation"
    assert driver.read_status().source == "simulation"
    assert driver.execute("$I").source == "simulation"
    assert driver.estop("test").source == "simulation"


def test_serial_backend_motion_in_simulate_mode_is_only_simulated():
    driver = make_driver()
    result = driver.execute(MotionCommand(x=1))
    assert result.ok is True
    assert result.source == "simulation"
    assert "gcode_preview" in result.data
