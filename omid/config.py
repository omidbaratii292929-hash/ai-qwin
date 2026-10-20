"""omid.config — پیکربندی مرکزی و اعتبارسنجی‌شده از متغیرهای محیطی.

اصول:
- هیچ رازی در کد وجود ندارد؛ توکن‌ها فقط از محیط خوانده می‌شوند.
- پیش‌فرض‌ها امن هستند: حالت simulate و قفل کنترل فیزیکی بسته.
- پیکربندی نامعتبر با :class:`~omid.errors.ConfigError` رد می‌شود (شکست صریح
  بهتر از رفتار تعریف‌نشده است).

© هوشمندسازی صنعت امید — OMID Industrial AI Agent
طراح و سازندهٔ اصلی: مهندس امید براتی
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from omid.errors import ConfigError

VALID_MODES: tuple[str, ...] = ("observe", "simulate", "control")


@dataclass(frozen=True)
class MachineLimits:
    """محدودهٔ کاری مجاز ماشین (برای اعتبارسنجی هر فرمان حرکتی)."""

    x_min: float = 0.0
    x_max: float = 300.0
    y_min: float = 0.0
    y_max: float = 300.0
    z_min: float = -50.0
    z_max: float = 0.0
    feed_min: float = 10.0
    feed_max: float = 2000.0

    def check_axis(self, axis: str, value: float) -> None:
        lo = getattr(self, f"{axis}_min")
        hi = getattr(self, f"{axis}_max")
        if not (lo <= value <= hi):
            raise ConfigError(f"مقدار محور {axis.upper()}={value} خارج از محدودهٔ مجاز [{lo}, {hi}] است.")


def _env_str(name: str, default: str) -> str:
    value = os.environ.get(name)
    return default if value is None or value.strip() == "" else value.strip()


def _env_str_opt(name: str) -> str | None:
    value = os.environ.get(name)
    return value.strip() if value is not None and value.strip() != "" else None


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"مقدار {name} باید عدد باشد: {raw!r}") from exc


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"مقدار {name} باید عدد صحیح باشد: {raw!r}") from exc


def _env_tuple(name: str) -> tuple[str, ...]:
    raw = os.environ.get(name)
    if not raw or not raw.strip():
        return ()
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _env_int_tuple(name: str, default: tuple[int, ...]) -> tuple[int, ...]:
    items = _env_tuple(name)
    if not items:
        return default
    try:
        return tuple(int(i) for i in items)
    except ValueError as exc:
        raise ConfigError(f"مقدار {name} باید فهرست اعداد صحیح جداشده با کاما باشد: {name}={items!r}") from exc


@dataclass(frozen=True)
class OMIDConfig:
    """پیکربندی کامل و تغییرناپذیر سامانه OMID."""

    mode: str = "simulate"
    allow_physical_control: bool = False
    data_dir: Path = field(default_factory=lambda: Path("data"))

    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = ""
    ollama_timeout: float = 30.0

    api_host: str = "127.0.0.1"
    api_port: int = 8000
    api_token: str | None = None
    control_token: str | None = None
    cors_origins: tuple[str, ...] = ()
    rate_limit_per_min: int = 240
    lang: str = "fa"

    network_allowlist: tuple[str, ...] = ()
    network_probe_ports: tuple[int, ...] = (502, 4840, 1883)

    limits: MachineLimits = field(default_factory=MachineLimits)

    def __post_init__(self) -> None:
        if self.mode not in VALID_MODES:
            raise ConfigError(f"حالت نامعتبر OMID_MODE={self.mode!r} — مقادیر مجاز: {VALID_MODES}")
        if not 1 <= self.api_port <= 65535:
            raise ConfigError(f"پورت نامعتبر: {self.api_port}")
        if self.ollama_timeout <= 0:
            raise ConfigError("OMID_OLLAMA_TIMEOUT باید بزرگ‌تر از صفر باشد.")
        if self.rate_limit_per_min <= 0:
            raise ConfigError("OMID_RATE_LIMIT_PER_MIN باید بزرگ‌تر از صفر باشد.")
        if self.lang not in {"fa", "en"}:
            raise ConfigError(f"زبان پشتیبانی‌نشده: {self.lang!r} (فقط fa یا en)")

    @classmethod
    def from_env(cls) -> OMIDConfig:
        """ساخت پیکربندی از متغیرهای محیطی با پیش‌فرض‌های امن."""
        return cls(
            mode=_env_str("OMID_MODE", "simulate").lower(),
            allow_physical_control=_env_bool("OMID_ALLOW_PHYSICAL_CONTROL", False),
            data_dir=Path(_env_str("OMID_DATA_DIR", "data")),
            ollama_url=_env_str("OMID_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/"),
            ollama_model=_env_str("OMID_OLLAMA_MODEL", ""),
            ollama_timeout=_env_float("OMID_OLLAMA_TIMEOUT", 30.0),
            api_host=_env_str("OMID_API_HOST", "127.0.0.1"),
            api_port=_env_int("OMID_API_PORT", 8000),
            api_token=_env_str_opt("OMID_API_TOKEN"),
            control_token=_env_str_opt("OMID_CONTROL_TOKEN"),
            cors_origins=_env_tuple("OMID_CORS_ORIGINS"),
            rate_limit_per_min=_env_int("OMID_RATE_LIMIT_PER_MIN", 240),
            lang=_env_str("OMID_LANG", "fa").lower(),
            network_allowlist=_env_tuple("OMID_NETWORK_ALLOWLIST"),
            network_probe_ports=_env_int_tuple("OMID_NETWORK_PROBE_PORTS", (502, 4840, 1883)),
        )

    def public_view(self) -> dict:
        """نمای قابل‌انتشار پیکربندی — بدون هیچ راز یا توکنی."""
        return {
            "mode_requested": self.mode,
            "allow_physical_control": self.allow_physical_control,
            "ollama_url": self.ollama_url,
            "ollama_model": self.ollama_model or None,
            "api_host": self.api_host,
            "api_port": self.api_port,
            "api_token_configured": self.api_token is not None,
            "control_token_configured": self.control_token is not None,
            "rate_limit_per_min": self.rate_limit_per_min,
            "lang": self.lang,
            "network_allowlist": list(self.network_allowlist),
            "network_probe_ports": list(self.network_probe_ports),
            "machine_limits": {
                "x": [self.limits.x_min, self.limits.x_max],
                "y": [self.limits.y_min, self.limits.y_max],
                "z": [self.limits.z_min, self.limits.z_max],
                "feed": [self.limits.feed_min, self.limits.feed_max],
            },
        }
