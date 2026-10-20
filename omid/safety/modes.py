"""omid.safety.modes — مدیر حالت‌های عملیاتی و توقف اضطراری.

سه سطح عملیات (اصل تفکیک مشاهده / پیشنهاد / شبیه‌سازی / اجرای فیزیکی):

- ``observe``   : فقط خواندن وضعیت و تحلیل (کم‌خطرترین).
- ``simulate``  : خواندن + پیشنهاد + شبیه‌سازی؛ هیچ فرمان فیزیکی صادر
  نمی‌شود. **حالت پیش‌فرض سامانه.**
- ``control``   : اجرای فیزیکی؛ تنها با سه قفل هم‌زمان ممکن است:
  1. ``OMID_ALLOW_PHYSICAL_CONTROL=1`` در پیکربندی محیط،
  2. عبارت تأیید صریح ``ENABLE-PHYSICAL-CONTROL`` در زمان درخواست،
  3. فعال نبودن توقف اضطراری.

توقف اضطراری (E-Stop):
- فعال‌سازی آن همیشه و بدون هیچ شرطی مجاز است (fail-safe).
- سامانه را بلافاصله به ``observe`` بازمی‌گرداند و هر عملیات ریسک‌دار
  (شبیه‌سازی حرکت و اجرای فیزیکی) را مسدود می‌کند.
- آزادسازی آن نیازمند اعتبار کنترل و عبارت تأیید صریح است.

این ماژول هیچ وابستگی به مدل زبانی یا لایهٔ برنامه‌ریزی ندارد.

© هوشمندسازی صنعت امید — OMID Industrial AI Agent
طراح و سازندهٔ اصلی: مهندس امید براتی
"""
from __future__ import annotations

import threading
from collections.abc import Callable
from enum import Enum

from omid.errors import SafetyError

CONTROL_CONFIRM_PHRASE = "ENABLE-PHYSICAL-CONTROL"
ESTOP_RELEASE_PHRASE = "RELEASE-ESTOP"

# نگاشت حداکثر ریسک مجاز در هر حالت (مقادیر با RiskLevel در core.permissions هم‌نام‌اند)
_MODE_MAX_RISK: dict[str, str] = {
    "observe": "read",
    "simulate": "simulate",
    "control": "physical",
}
_RISK_RANK = {"read": 0, "suggest": 1, "simulate": 2, "physical": 3}


class OperationMode(str, Enum):
    OBSERVE = "observe"
    SIMULATE = "simulate"
    CONTROL = "control"


class SafetyManager:
    """نگهبان مرکزی حالت عملیاتی و توقف اضطراری (thread-safe)."""

    def __init__(
        self,
        *,
        requested_mode: str = "simulate",
        allow_physical_control: bool = False,
        audit: Callable[..., None] | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._allow_physical_control = bool(allow_physical_control)
        self._audit = audit or (lambda *a, **k: None)
        self._estop_active = False
        self._estop_reason: str | None = None
        self._estop_at: str | None = None

        mode = requested_mode if requested_mode in _MODE_MAX_RISK else "simulate"
        if mode == "control" and not self._allow_physical_control:
            # قفل سخت‌افزاری بسته است → downgrade امن با ثبت صریح
            self._audit(
                "safety.mode_downgraded",
                "حالت control درخواست شده بود اما OMID_ALLOW_PHYSICAL_CONTROL غیرفعال است؛ "
                "به حالت simulate تنزل یافت (پیش‌فرض امن).",
                severity="warning",
            )
            mode = "simulate"
        self._mode = mode

    # ---------- وضعیت ----------
    @property
    def mode(self) -> str:
        with self._lock:
            return self._mode

    @property
    def estop_active(self) -> bool:
        with self._lock:
            return self._estop_active

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "mode": self._mode,
                "max_risk_in_mode": _MODE_MAX_RISK[self._mode],
                "estop_active": self._estop_active,
                "estop_reason": self._estop_reason,
                "estop_at": self._estop_at,
                "allow_physical_control_configured": self._allow_physical_control,
                "control_confirm_phrase_required": CONTROL_CONFIRM_PHRASE,
            }

    # ---------- تغییر حالت ----------
    def request_mode(self, new_mode: str, confirm: str = "", *, source: str = "api") -> str:
        """تغییر حالت عملیاتی با قفل‌های صریح؛ در صورت نقض، SafetyError."""
        if new_mode not in _MODE_MAX_RISK:
            raise SafetyError(f"حالت نامعتبر: {new_mode!r} — مقادیر مجاز: {sorted(_MODE_MAX_RISK)}")
        with self._lock:
            if self._estop_active and new_mode != "observe":
                raise SafetyError("توقف اضطراری فعال است؛ فقط انتقال به observe ممکن است.")
            if new_mode == "control":
                if not self._allow_physical_control:
                    raise SafetyError(
                        "کنترل فیزیکی در پیکربندی محیط غیرفعال است (OMID_ALLOW_PHYSICAL_CONTROL=0)."
                    )
                if confirm != CONTROL_CONFIRM_PHRASE:
                    raise SafetyError(
                        f"ورود به حالت control نیازمند تأیید صریح است (confirm={CONTROL_CONFIRM_PHRASE!r})."
                    )
            old = self._mode
            self._mode = new_mode
        self._audit(
            "safety.mode_changed",
            f"حالت عملیاتی از {old} به {new_mode} تغییر کرد.",
            data={"from": old, "to": new_mode, "source": source},
            severity="audit",
        )
        return new_mode

    # ---------- توقف اضطراری (مسیر مستقل از LLM) ----------
    def trigger_estop(self, reason: str = "", *, source: str = "operator") -> dict:
        """فعال‌سازی توقف اضطراری — همیشه مجاز، بدون هیچ پیش‌شرطی."""
        from omid.events import utc_now_iso

        with self._lock:
            self._estop_active = True
            self._estop_reason = reason or "بدون دلیل ثبت‌شده"
            self._estop_at = utc_now_iso()
            downgraded = self._mode != "observe"
            self._mode = "observe"
        self._audit(
            "safety.estop_triggered",
            f"توقف اضطراری فعال شد ({self._estop_reason})."
            + (" حالت به observe تنزل یافت." if downgraded else ""),
            data={"reason": self._estop_reason, "source": source, "downgraded": downgraded},
            severity="critical",
        )
        return self.snapshot()

    def release_estop(self, confirm: str = "", *, source: str = "operator") -> dict:
        """آزادسازی توقف اضطراری فقط با عبارت تأیید صریح؛ حالت observe می‌ماند."""
        if confirm != ESTOP_RELEASE_PHRASE:
            raise SafetyError(
                f"آزادسازی توقف اضطراری نیازمند تأیید صریح است (confirm={ESTOP_RELEASE_PHRASE!r})."
            )
        with self._lock:
            self._estop_active = False
            reason, at = self._estop_reason, self._estop_at
            self._estop_reason = None
            self._estop_at = None
            self._mode = "observe"
        self._audit(
            "safety.estop_released",
            "توقف اضطراری آزاد شد؛ حالت روی observe باقی ماند و ارتقا نیازمند درخواست جداگانه است.",
            data={"previous_reason": reason, "previous_at": at, "source": source},
            severity="audit",
        )
        return self.snapshot()

    # ---------- دروازهٔ ریسک ----------
    def assert_allowed(self, risk: str, *, context: str = "") -> None:
        """بررسی مجاز بودن سطح ریسک در حالت فعلی؛ در صورت نقض SafetyError."""
        risk_value = risk.value if isinstance(risk, Enum) else str(risk)
        with self._lock:
            if self._estop_active and _RISK_RANK.get(risk_value, 3) >= _RISK_RANK["simulate"]:
                raise SafetyError(
                    f"توقف اضطراری فعال است؛ عملیات ریسک‌دار ({risk_value}) مسدود است. {context}".strip()
                )
            max_risk = _MODE_MAX_RISK[self._mode]
            if _RISK_RANK.get(risk_value, 3) > _RISK_RANK[max_risk]:
                raise SafetyError(
                    f"عملیات با ریسک «{risk_value}» در حالت «{self._mode}» مجاز نیست "
                    f"(حداکثر مجاز: {max_risk}). {context}".strip()
                )

    def is_allowed(self, risk: str) -> bool:
        try:
            self.assert_allowed(risk)
            return True
        except SafetyError:
            return False
