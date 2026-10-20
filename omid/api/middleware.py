"""omid.api.middleware — rate limiting ساده و سرصفحه‌های امنیتی.

© هوشمندسازی صنعت امید — OMID Industrial AI Agent
"""
from __future__ import annotations

import threading
import time
from collections import deque

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    ),
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """محدودساز نرخ in-memory بر اساس کلاینت (مناسب تک‌گرهٔ LAN)."""

    def __init__(self, app, *, limit_per_min: int, exempt_prefixes: tuple[str, ...] = ()) -> None:  # noqa: ANN001
        super().__init__(app)
        self.limit = max(1, limit_per_min)
        self.exempt = exempt_prefixes
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _client_key(self, request: Request) -> str:
        client = request.client.host if request.client else "unknown"
        auth = request.headers.get("authorization", "")
        # کلید = ip + اثر انگشت توکن (بدون ذخیرهٔ خود توکن)
        return f"{client}:{hash(auth) & 0xFFFFFFFF:08x}"

    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        path = request.url.path
        if not path.startswith("/api") or any(path.startswith(p) for p in self.exempt):
            return await call_next(request)
        key = self._client_key(request)
        now = time.monotonic()
        with self._lock:
            window = self._hits.setdefault(key, deque())
            while window and now - window[0] > 60.0:
                window.popleft()
            if len(window) >= self.limit:
                retry_after = int(60.0 - (now - window[0])) + 1
                return JSONResponse(
                    status_code=429,
                    content={"detail": "محدودیت نرخ درخواست پر شد. کمی بعد تلاش کنید."},
                    headers={"Retry-After": str(retry_after)},
                )
            window.append(now)
            # جلوگیری از رشد بی‌نهایت دیکشنری کلاینت‌ها
            if len(self._hits) > 10_000:
                for old_key in list(self._hits)[: len(self._hits) // 2]:
                    self._hits.pop(old_key, None)
        return await call_next(request)
