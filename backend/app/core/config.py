from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # API
    api_v1_prefix: str = "/api/v1"

    # Database - Railway provides MYSQL_URL or DATABASE_URL
    database_url: Optional[str] = Field(default=None, validation_alias="DATABASE_URL")
    mysql_url: Optional[str] = Field(default=None, validation_alias="MYSQL_URL")

    # Database (MySQL) - fallback for local development
    mysql_host: str = Field(default="db", validation_alias="MYSQL_HOST")
    mysql_port: int = Field(default=3306, validation_alias="MYSQL_PORT")
    mysql_user: str = Field(default="tenant_ai", validation_alias="MYSQL_USER")
    mysql_password: str = Field(default="tenant_ai", validation_alias="MYSQL_PASSWORD")
    mysql_db: str = Field(default="tenant_ai", validation_alias="MYSQL_DB")

    # OpenAI
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    # Use the top-tier embedding model per OpenAI docs.
    openai_embedding_model: str = Field(default="text-embedding-3-large", validation_alias="OPENAI_EMBEDDING_MODEL")

    # Gemini
    gemini_api_key: str = Field(default="", validation_alias="GEMINI_API_KEY")
    # Chunking (OCR + image understanding): use the top model (Gemini 3 Pro Preview)
    gemini_chunk_model: str = Field(default="gemini-3-pro-preview", validation_alias="GEMINI_CHUNK_MODEL")
    # Chat answering: use Gemini 3 Flash Preview
    gemini_chat_model: str = Field(default="gemini-3-flash-preview", validation_alias="GEMINI_CHAT_MODEL")
    # Image answering: use Gemini 3 Pro Preview (higher accuracy for image recognition)
    gemini_image_model: str = Field(default="gemini-3-pro-preview", validation_alias="GEMINI_IMAGE_MODEL")

    # Storage - Railway volume mount path can be configured via env
    storage_dir: Path = Field(default=Path("/app/storage"), validation_alias="STORAGE_DIR")
    backend_public_url: str = Field(default="http://localhost:8000", validation_alias="BACKEND_PUBLIC_URL")

    @field_validator("storage_dir", mode="before")
    @classmethod
    def _parse_storage_dir(cls, v):
        if isinstance(v, str):
            return Path(v)
        return v

    # CORS
    cors_origins: List[str] = Field(default_factory=lambda: ["http://localhost:3000"], validation_alias="CORS_ORIGINS")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v):
        # Allow JSON array or comma-separated string in env var.
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return [str(s).strip() for s in parsed if str(s).strip()]
            if isinstance(parsed, str):
                return [parsed.strip()] if parsed.strip() else []
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    # Derived directories
    @property
    def uploads_dir(self) -> Path:
        return self.storage_dir / "uploads"

    @property
    def images_dir(self) -> Path:
        return self.storage_dir / "images"

    @property
    def faiss_dir(self) -> Path:
        return self.storage_dir / "faiss"

    @property
    def tmp_dir(self) -> Path:
        return self.storage_dir / "tmp"

    @property
    def chunk_faiss_dir(self) -> Path:
        return self.faiss_dir / "chunk_faiss"

    @property
    def faq_faiss_dir(self) -> Path:
        return self.faiss_dir / "faq_faiss"


settings = Settings()
