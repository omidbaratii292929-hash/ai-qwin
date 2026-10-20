"""omid.safety.validator — اعتبارسنجی فرمان‌ها و محافظ G-code.

قواعد بنیادین:
- **G-code خام تولیدشده توسط مدل زبانی هرگز مستقیماً ارسال نمی‌شود.**
  فقط فرمان‌های خواندن وضعیت (whitelist) اجازهٔ عبور دارند؛ حرکت باید از
  مسیر ساختاریافتهٔ :class:`MotionCommand` و اعتبارسنجی محدوده بگذرد.
- هر فرمان حرکتی پیش از اجرا باید با حدود ماشین بررسی شود.

© هوشمندسازی صنعت امید — OMID Industrial AI Agent
طراح و سازندهٔ اصلی: مهندس امید براتی
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from omid.config import MachineLimits
from omid.errors import ValidationError

# فرمان‌های فقط‌خواندنی GRBL که عبورشان بی‌خطر است (بدون اثر حرکتی/خروجی)
READONLY_GCODE_WHITELIST: frozenset[str] = frozenset({"?", "$$", "$#", "$i", "$g", "$n", "$c"})

_PAREN_COMMENT = re.compile(r"\([^)]*\)")


# کلمات محرک حرکت یا خروجی فیزیکی — عبور متن خام حاوی این‌ها ممنوع است
_MOTION_PATTERN = re.compile(
    r"\b(g0*[\d]|g1|g2|g3|g4|g2[08]|g3[08]|g9[012]|m[0-9]|x-?[\d.]+|y-?[\d.]+|z-?[\d.]+|f[\d.]+|s[\d.]+)\b",
    re.I,
)


def strip_comments(line: str) -> str:
    """حذف کامنت‌های G-code (پرانتز و ;) و فاصله‌های اضافی."""
    line = _PAREN_COMMENT.sub(" ", line)
    line = line.split(";", 1)[0]
    return line.strip()


def screen_gcode_line(line: str) -> tuple[bool, str, str]:
    """غربالگری یک خط G-code خام.

    Returns:
        (allowed, normalized, reason)
    """
    normalized = strip_comments(line).lower()
    if not normalized:
        return False, "", "خط خالی یا فقط کامنت."
    if normalized in READONLY_GCODE_WHITELIST:
        return True, normalized, "فرمان فقط‌خواندنی مجاز (whitelist)."
    if _MOTION_PATTERN.search(normalized):
        return (
            False,
            normalized,
            "فرمان حرکتی/خروجی خام مسدود شد؛ G-code خام (به‌ویژه از متن مدل زبانی) "
            "هرگز مستقیم ارسال نمی‌شود. از MotionCommand ساختاریافته استفاده کنید.",
        )
    return False, normalized, f"فرمان ناشناخته «{normalized}» خارج از whitelist فقط‌خواندنی است."


@dataclass(frozen=True)
class MotionCommand:
    """فرمان حرکتی ساختاریافته — تنها مسیر مجاز درخواست حرکت."""

    x: float | None = None
    y: float | None = None
    z: float | None = None
    feed: float | None = None

    def validate(self, limits: MachineLimits) -> None:
        """اعتبارسنجی با حدود ماشین؛ در صورت تخلف ValidationError."""
        if all(v is None for v in (self.x, self.y, self.z)):
            raise ValidationError("فرمان حرکتی باید حداقل یک محور هدف داشته باشد.")
        for axis, value in (("x", self.x), ("y", self.y), ("z", self.z)):
            if value is not None:
                try:
                    float(value)
                except (TypeError, ValueError) as exc:
                    raise ValidationError(f"مقدار محور {axis.upper()} عددی نیست: {value!r}") from exc
                if not (limits.__getattribute__(f"{axis}_min") <= value <= limits.__getattribute__(f"{axis}_max")):
                    lo = limits.__getattribute__(f"{axis}_min")
                    hi = limits.__getattribute__(f"{axis}_max")
                    raise ValidationError(
                        f"مقدار محور {axis.upper()}={value} خارج از محدودهٔ مجاز [{lo}, {hi}] است."
                    )
        if self.feed is not None:
            if not (limits.feed_min <= self.feed <= limits.feed_max):
                raise ValidationError(
                    f"فید {self.feed} خارج از محدودهٔ مجاز [{limits.feed_min}, {limits.feed_max}] است."
                )

    def to_gcode(self) -> str:
        """تولید G-code — فقط پس از validate() و فقط داخل درایور مجاز استفاده شود."""
        parts = ["G1"]
        if self.x is not None:
            parts.append(f"X{self.x:.3f}")
        if self.y is not None:
            parts.append(f"Y{self.y:.3f}")
        if self.z is not None:
            parts.append(f"Z{self.z:.3f}")
        if self.feed is not None:
            parts.append(f"F{self.feed:.0f}")
        return " ".join(parts)

    def to_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "z": self.z, "feed": self.feed}


def validate_motion(command: MotionCommand, limits: MachineLimits) -> MotionCommand:
    """اعتبارسنجی فرمان حرکتی و بازگرداندن همان فرمان (برای زنجیره‌سازی)."""
    command.validate(limits)
    return command
