from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.database import engine
from app.models.base import Base
from app.services.document_processor import ensure_storage_dirs


app = FastAPI(title="テナントAIアシスタント API", version="1.0.0")


# CORS - temporarily allow all origins for debugging
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # Must be False when using "*"
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static (only images)
# URL: /static/images/... -> storage/images/...
ensure_storage_dirs()
app.mount("/static/images", StaticFiles(directory=str(settings.images_dir)), name="images")


@app.on_event("startup")
async def on_startup() -> None:
    # Create tables (MVP: auto-create)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/health")
async def health():
    return {"status": "ok"}
