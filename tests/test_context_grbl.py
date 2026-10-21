"""ApplicationContext GRBL backend wiring tests; never open a physical port."""
from __future__ import annotations

from omid.config import OMIDConfig
from omid.context import AppContext
from omid.drivers.base import CommandResult


def test_context_uses_explicit_serial_backend_and_reports_failed_connection(monkeypatch, tmp_path):
    def fail_connect(driver):
        assert driver.backend == "serial"
        assert driver.serial_port == "COM_TEST"
        return CommandResult(ok=False, error="synthetic connection failure", source="live")

    monkeypatch.setattr("omid.context.GRBLDriver.connect", fail_connect)
    config = OMIDConfig(
        mode="simulate",
        data_dir=tmp_path / "data",
        grbl_backend="serial",
        grbl_serial_port="COM_TEST",
        grbl_baudrate=115200,
        ollama_url="http://127.0.0.1:9",
        ollama_timeout=0.1,
    )
    ctx = AppContext(config)
    try:
        assert ctx.grbl.backend == "serial"
        assert ctx.grbl.serial_port == "COM_TEST"
        assert ctx.grbl_connection.ok is False
        assert ctx.status()["grbl_connection"]["ok"] is False
        check = ctx.selfcheck()
        assert check["checks"]["grbl_connection"]["ok"] is False
        assert check["overall_ok"] is False
    finally:
        ctx.close()


def test_context_defaults_to_connected_simulator(tmp_path):
    config = OMIDConfig(data_dir=tmp_path / "data", ollama_url="http://127.0.0.1:9", ollama_timeout=0.1)
    ctx = AppContext(config)
    try:
        assert ctx.grbl.backend == "simulated"
        assert ctx.grbl_connection.ok is True
        assert ctx.grbl_connection.source == "simulation"
    finally:
        ctx.close()
