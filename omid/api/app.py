"""omid.api.app — کارخانهٔ ساخت اپلیکیشن FastAPI.

- احراز هویت تفکیک‌شده (خواندن/کنترل) — omid.api.auth
- محدودسازی نرخ و سرصفحه‌های امنیتی — omid.api.middleware
- CORS فقط در صورت پیکربندی صریح origins
- داشبورد ایستا روی /dashboard (بدون هیچ منبع خارجی/CDN)
- هیچ رازی در پاسخ‌ها، خطاها یا لاگ‌ها بازنویسی نمی‌شود

© هوشمندسازی صنعت امید — OMID Industrial AI Agent
طراح و سازندهٔ اصلی: مهندس امید براتی
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from omid import __version__, branding
from omid.api.middleware import RateLimitMiddleware, SecurityHeadersMiddleware
from omid.api.routers import agent, devices, knowledge, safety, status
from omid.context import AppContext

_DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard" / "static"


def create_app(ctx: AppContext | None = None) -> FastAPI:
    """ساخت اپلیکیشن با Context تزریق‌شده یا ساخته‌شده از محیط."""
    context = ctx or AppContext()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        context.close()

    brand = branding.load_branding()
    app = FastAPI(
        title=f"{brand['project_name']} API",
        description=(
            f"{brand['company_name']} — {brand['tagline']}\n\n"
            f"طراح و سازندهٔ اصلی: {brand['lead_designer_and_creator']}\n"
            f"با همکاری: {' و '.join(brand['collaborators'])}"
        ),
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.ctx = context

    # middlewares (ترتیب: هدرها → نرخ → handler)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        RateLimitMiddleware,
        limit_per_min=context.config.rate_limit_per_min,
        exempt_prefixes=("/api/health",),
    )
    if context.config.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(context.config.cors_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "X-OMID-Control-Token"],
        )

    for module in (status, agent, safety, devices, knowledge):
        app.include_router(module.router)

    if _DASHBOARD_DIR.is_dir():
        app.mount("/dashboard", StaticFiles(directory=str(_DASHBOARD_DIR), html=True), name="dashboard")

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/dashboard/")

    return app
