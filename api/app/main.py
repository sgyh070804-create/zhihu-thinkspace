from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import auth, bubbles, extension, zhihu_data
from .config import Settings
from .providers.zhihu import ZhihuClient, ZhihuError
from .store import Store


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(title="ThinkSpace API", version="0.1.0")
    app.state.settings = settings
    app.state.store = Store(settings.database_path, settings.secret_key)
    app.state.zhihu = ZhihuClient(settings)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_url],
        allow_origin_regex=r"^chrome-extension://.*$",
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.exception_handler(ZhihuError)
    async def zhihu_error_handler(_: Request, exc: ZhihuError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": {"code": exc.code, "message": exc.message}},
        )

    @app.get("/api/health")
    def health() -> dict:
        return {
            "status": "ok",
            "oauth_configured": settings.oauth_configured,
            "demo_enabled": settings.enable_demo,
        }

    app.include_router(auth.router)
    app.include_router(zhihu_data.router)
    app.include_router(bubbles.router)
    app.include_router(extension.router)
    return app


app = create_app()
