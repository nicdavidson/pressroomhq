"""Pressroom — Marketing Department in a Box."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from database import init_db
from api.signals import router as signals_router
from api.content import router as content_router
from api.pipeline import router as pipeline_router
from api.webhook import router as webhook_router
from api.publish import router as publish_router
from api.settings import router as settings_router
from api.imports import router as imports_router
from api.onboard import router as onboard_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="Pressroom",
    description="This just in: your story's already written.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
async def health():
    return {"status": "on the wire", "version": "0.1.0"}

app.include_router(signals_router)
app.include_router(content_router)
app.include_router(pipeline_router)
app.include_router(webhook_router)
app.include_router(publish_router)
app.include_router(settings_router)
app.include_router(imports_router)
app.include_router(onboard_router)

# Serve frontend static files if built — MUST be last (catch-all)
frontend_dist = Path(__file__).parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
