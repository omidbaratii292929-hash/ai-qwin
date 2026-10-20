"""omid.ai.ollama — کلاینت Ollama با بررسی سلامت و degradation صادقانه.

- هیچ endpoint، نام مدل یا قابلیتی فرض نمی‌شود؛ اول سلامت سرویس و وجود
  مدل بررسی می‌شود.
- هر خطای شبکه/سرویس به :class:`ProviderResult` با ``ok=False`` و پیام
  صادقانه تبدیل می‌شود (بدون exception به بیرون).
- زمان‌سنجی درخواست (latency_ms) برای گزارش‌های تشخیصی ثبت می‌شود.

© هوشمندسازی صنعت امید — OMID Industrial AI Agent
طراح و سازندهٔ اصلی: مهندس امید براتی
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class HealthStatus:
    available: bool
    models: list[str] = field(default_factory=list)
    latency_ms: float | None = None
    error: str | None = None
    checked_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "models": self.models,
            "latency_ms": self.latency_ms,
            "error": self.error,
        }


@dataclass
class ProviderResult:
    ok: bool
    text: str = ""
    error: str | None = None
    latency_ms: float | None = None
    provider: str = "ollama"
    model: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "text": self.text,
            "error": self.error,
            "latency_ms": self.latency_ms,
            "provider": self.provider,
            "model": self.model,
        }


class OllamaProvider:
    """کلاینت HTTP سرویس Ollama (محلی) با رفتار دفاعی."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "",
        timeout: float = 30.0,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = max(1.0, timeout)
        self._client = client or httpx.Client(timeout=self.timeout)

    # ---------- سلامت ----------
    def health(self) -> HealthStatus:
        started = time.monotonic()
        try:
            resp = self._client.get(f"{self.base_url}/api/tags", timeout=min(5.0, self.timeout))
            latency = round((time.monotonic() - started) * 1000, 1)
            if resp.status_code != 200:
                return HealthStatus(False, [], latency, f"Ollama پاسخ نامعتبر داد (HTTP {resp.status_code}).")
            payload = resp.json()
            models = [m.get("name", "") for m in payload.get("models", []) if isinstance(m, dict)]
            return HealthStatus(True, models, latency, None)
        except httpx.HTTPError as exc:
            latency = round((time.monotonic() - started) * 1000, 1)
            return HealthStatus(False, [], latency, f"Ollama در دسترس نیست ({self.base_url}): {type(exc).__name__}")
        except ValueError:
            return HealthStatus(False, [], None, "پاسخ Ollama JSON معتبر نبود.")

    def model_available(self, name: str | None = None) -> bool:
        target = (name or self.model).strip()
        status = self.health()
        if not status.available:
            return False
        if not target:
            return True  # سرویس سالم است و مدل خاصی درخواست نشده
        return any(m == target or m.startswith(target + ":") for m in status.models)

    # ---------- گفت‌وگو ----------
    def chat(self, messages: list[dict[str, str]], *, timeout: float | None = None) -> ProviderResult:
        if not self.model:
            return ProviderResult(
                ok=False,
                error="مدل زبانی پیکربندی نشده است (OMID_OLLAMA_MODEL خالی است). سامانه در حالت قواعد-محور ادامه می‌دهد.",
                model="",
            )
        started = time.monotonic()
        try:
            resp = self._client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": 0.2},
                },
                timeout=timeout or self.timeout,
            )
            latency = round((time.monotonic() - started) * 1000, 1)
            if resp.status_code != 200:
                return ProviderResult(
                    ok=False,
                    error=f"Ollama خطا داد (HTTP {resp.status_code}): {resp.text[:200]}",
                    latency_ms=latency,
                    model=self.model,
                )
            payload = resp.json()
            text = (payload.get("message") or {}).get("content", "")
            return ProviderResult(ok=True, text=text, latency_ms=latency, model=self.model)
        except httpx.HTTPError as exc:
            latency = round((time.monotonic() - started) * 1000, 1)
            return ProviderResult(
                ok=False,
                error=f"خطای ارتباط با Ollama: {type(exc).__name__}",
                latency_ms=latency,
                model=self.model,
            )
        except ValueError:
            return ProviderResult(ok=False, error="پاسخ Ollama JSON معتبر نبود.", model=self.model)

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:  # noqa: BLE001
            pass
