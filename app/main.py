"""MidasClick — FastAPI application factory and lifecycle."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.mongodb import connect_to_mongo, close_mongo_connection


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await connect_to_mongo()
    yield
    await close_mongo_connection()


def create_app() -> FastAPI:
    app = FastAPI(
        title="MidasClick API",
        version="0.1.0",
        description="Job Application Manager & Resume Optimizer",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Register routers ──────────────────────────
    from app.api.v1.applications import router as apps_router
    from app.api.v1.resumes import router as resumes_router
    from app.api.v1.jobs import router as jobs_router
    from app.api.v1.analytics import router as analytics_router
    from app.api.v1.tailoring import router as tailoring_router

    app.include_router(apps_router, prefix="/api/v1")
    app.include_router(resumes_router, prefix="/api/v1")
    app.include_router(jobs_router, prefix="/api/v1")
    app.include_router(analytics_router, prefix="/api/v1")
    app.include_router(tailoring_router, prefix="/api/v1")

    @app.get("/health")
    async def health():
        return {"status": "ok", "version": "0.1.0"}

    return app


app = create_app()
