"""آزمون اعتبارسنج فرمان‌ها و محافظ G-code."""
from __future__ import annotations

import pytest

from omid.config import MachineLimits
from omid.errors import ValidationError
from omid.safety.validator import MotionCommand, screen_gcode_line, validate_motion


def test_motion_valid():
    cmd = MotionCommand(x=10, y=20, z=-5, feed=500)
    validate_motion(cmd, MachineLimits())
    assert cmd.to_gcode() == "G1 X10.000 Y20.000 Z-5.000 F500"


def test_motion_requires_axis():
    with pytest.raises(ValidationError):
        validate_motion(MotionCommand(feed=100), MachineLimits())


def test_motion_out_of_range_rejected():
    limits = MachineLimits()
    with pytest.raises(ValidationError):
        validate_motion(MotionCommand(x=99999), limits)
    with pytest.raises(ValidationError):
        validate_motion(MotionCommand(z=10), limits)  # z_max = 0
    with pytest.raises(ValidationError):
        validate_motion(MotionCommand(x=1, feed=999999), limits)


def test_motion_non_numeric_rejected():
    with pytest.raises(ValidationError):
        validate_motion(MotionCommand(x="abc"), MachineLimits())  # type: ignore[arg-type]


@pytest.mark.parametrize("line", ["?", "$$", "$I", "$i", "$G", "$g", "$N", "$n", "$#", "  ?  ", "? ; comment", "(note) $$"])
def test_readonly_gcode_allowed(line):
    allowed, normalized, _ = screen_gcode_line(line)
    assert allowed is True
    assert normalized in {"?", "$$", "$I", "$G", "$N", "$#"}


@pytest.mark.parametrize(
    "line",
    ["G1 X10 Y10", "g0 x0", "M3 S1000", "M5", "G90", "X100", "F500", "G54", "$J=X10", "S9999"],
)
def test_motion_gcode_raw_blocked(line):
    allowed, _, reason = screen_gcode_line(line)
    assert allowed is False
    assert reason  # دلیل صادقانه


def test_unknown_command_blocked():
    allowed, _, reason = screen_gcode_line("DANCE")
    assert allowed is False
    assert "whitelist" in reason


def test_empty_line_blocked():
    allowed, _, _ = screen_gcode_line("   ")
    assert allowed is False


def test_check_mode_is_not_readonly():
    allowed, _, reason = screen_gcode_line("$C")
    assert allowed is False
    assert reason


def test_unsupported_case_variant_is_not_canonicalized():
    allowed, normalized, _ = screen_gcode_line("$c")
    assert allowed is False
    assert normalized == "$c"
