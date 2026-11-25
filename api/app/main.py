from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import auth, bubbles, discussion_engine_api, discussions, extension, qa_api, thoughts, zhihu_data
from .config import Settings
from .discussion_engine import DiscussionEngine
from .discussion_store import DiscussionStore
from .providers.model import build_model
from .providers.zhihu import ZhihuClient, ZhihuError
from .qa import QAService, SummaryAnswerModel
from .qa_store import QAStore
from .store import Store


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(title="ThinkSpace API", version="0.1.0")
    app.state.settings = settings
    app.state.store = Store(settings.database_path, settings.secret_key)
    # 讨论室的表引用 users，因此必须在 Store 建好用户表之后再初始化。
    app.state.discussions = DiscussionStore(settings.database_path)
    # 收藏问答与会话/泡泡共用 users 表，必须在 Store 之后初始化。
    app.state.qa_store = QAStore(settings.database_path)
    # E 模块只依赖讨论存储的公开方法；模型实现由配置决定（目前是确定性假模型）。
    app.state.engine = DiscussionEngine(app.state.discussions, build_model(settings))
    app.state.zhihu = ZhihuClient(settings)
    # 收藏问答首版用摘要抽取，不调用生成模型。
    app.state.qa = QAService(app.state.qa_store, app.state.zhihu, SummaryAnswerModel())

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
    app.include_router(thoughts.router)
    app.include_router(extension.router)
    app.include_router(discussions.router)
    app.include_router(discussion_engine_api.router)
    app.include_router(qa_api.router)
    return app


app = create_app()
