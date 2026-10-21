"""Regression tests for truthful serial backend behavior; no physical hardware is used."""
from __future__ import annotations

from unittest.mock import MagicMock

from omid.drivers.grbl import GRBLDriver
from omid.safety.modes import CONTROL_CONFIRM_PHRASE, SafetyManager
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
    driver._write_raw = MagicMock(side_effect=[False, True])
    result = driver.estop("test")
    assert result.ok is False
    assert result.source == "live"
    assert result.data["physical_stop_confirmed"] is False


def test_estop_only_reports_io_confirmed_when_both_writes_succeed():
    driver = make_driver()
    driver._serial = MagicMock()
    driver._write_raw = MagicMock(side_effect=[True, True])
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



def test_live_motion_rejects_grbl_error_reply():
    safety = SafetyManager(requested_mode="simulate", allow_physical_control=True)
    safety.request_mode("control", confirm=CONTROL_CONFIRM_PHRASE)
    driver = GRBLDriver(backend="serial", serial_port="COM_TEST", safety=safety)
    driver._serial = MagicMock()
    driver._send_command = MagicMock(return_value="error:15")
    previous_position = list(driver._sim_position)
    result = driver.execute(MotionCommand(x=10))
    assert result.ok is False
    assert result.source == "live"
    assert "error:15" in (result.error or "")
    assert driver._sim_position == previous_position


def test_live_motion_timeout_does_not_claim_success():
    safety = SafetyManager(requested_mode="simulate", allow_physical_control=True)
    safety.request_mode("control", confirm=CONTROL_CONFIRM_PHRASE)
    driver = GRBLDriver(backend="serial", serial_port="COM_TEST", safety=safety)
    driver._serial = MagicMock()
    driver._send_command = MagicMock(return_value=None)
    result = driver.execute(MotionCommand(x=10))
    assert result.ok is False
    assert result.source == "live"


def test_live_status_requires_valid_status_frame():
    driver = make_driver()
    driver._serial = MagicMock()
    driver._send_raw = MagicMock(return_value="")
    result = driver.read_status()
    assert result.ok is False
    assert result.source == "live"


def test_live_readonly_command_rejects_empty_response():
    driver = make_driver()
    driver._serial = MagicMock()
    driver._send_command = MagicMock(return_value=None)
    result = driver.execute("$I")
    assert result.ok is False
    assert result.source == "live"


def test_send_command_timeout_returns_none():
    driver = make_driver()
    serial_port = MagicMock()
    serial_port.write.return_value = len(b"$I\n")
    serial_port.readline.return_value = b""
    driver._serial = serial_port
    result = driver._send_command("$I\n")
    assert result is None


def test_estop_realtime_writes_do_not_wait_for_line_ack():
    driver = make_driver()
    serial_port = MagicMock()
    serial_port.write.side_effect = [1, 1]
    driver._serial = serial_port
    result = driver.estop("test")
    assert result.ok is True
    assert result.source == "live"
    assert result.data["stop_commands_sent"] is True
    assert result.data["physical_stop_confirmed"] is False
    assert [call.args[0] for call in serial_port.write.call_args_list] == [b"!", b"\x18"]
    serial_port.readline.assert_not_called()



def test_send_command_collects_multiline_response_until_ok():
    driver = make_driver()
    serial_port = MagicMock()
    serial_port.timeout = 2.0
    serial_port.write.return_value = len(b"$$\n")
    serial_port.readline.side_effect = [b"$0=10\r\n", b"$1=25\r\n", b"ok\r\n"]
    driver._serial = serial_port

    response = driver._send_command("$$\n")

    assert response == "$0=10\n$1=25\nok"
    assert serial_port.readline.call_count == 3
    assert serial_port.timeout == 2.0  # original timeout restored


def test_send_command_preserves_multiline_error_terminator():
    driver = make_driver()
    serial_port = MagicMock()
    serial_port.timeout = 2.0
    serial_port.write.return_value = len(b"$$\n")
    serial_port.readline.side_effect = [b"$0=10\r\n", b"error:2\r\n"]
    driver._serial = serial_port

    response = driver._send_command("$$\n")

    assert response == "$0=10\nerror:2"
    assert serial_port.readline.call_count == 2


def test_live_readonly_query_returns_all_lines_from_controller():
    driver = make_driver()
    driver._serial = MagicMock()
    driver._send_command = MagicMock(return_value="$0=10\n$1=25\nok")

    result = driver.execute("$$")

    assert result.ok is True
    assert result.source == "live"
    assert result.data["response"] == "$0=10\n$1=25\nok"
    driver._send_command.assert_called_once_with("$$\n")



def test_live_readonly_status_command_rejects_invalid_frame():
    driver = make_driver()
    driver._serial = MagicMock()
    driver._send_raw = MagicMock(return_value="not a GRBL status frame")
    result = driver.execute("?")
    assert result.ok is False
    assert result.source == "live"
