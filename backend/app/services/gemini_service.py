from __future__ import annotations

from typing import Any, Optional, Type, TypeVar

from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from google import genai
from google.genai import types

from app.core.config import settings


T = TypeVar("T", bound=BaseModel)


def _make_client() -> genai.Client:
    # The SDK can also pick up the API key from GEMINI_API_KEY env var.
    if settings.gemini_api_key:
        return genai.Client(api_key=settings.gemini_api_key)
    return genai.Client()


_client = _make_client()


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(Exception),
)
async def generate_text(
    *,
    model: str,
    contents: Any,
    config: Optional[dict[str, Any]] = None,
) -> str:
    response = await _client.aio.models.generate_content(
        model=model,
        contents=contents,
        config=config,
    )
    return (response.text or "").strip()


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(Exception),
)
async def generate_structured(
    *,
    model: str,
    contents: Any,
    schema_model: Type[T],
    config: Optional[dict[str, Any]] = None,
) -> T:
    # Structured Outputs: set response_mime_type="application/json" and provide response_json_schema.
    cfg: dict[str, Any] = {}
    if config:
        cfg.update(config)
    cfg.update(
        {
            "response_mime_type": "application/json",
            "response_json_schema": schema_model.model_json_schema(),
        }
    )

    response = await _client.aio.models.generate_content(
        model=model,
        contents=contents,
        config=cfg,
    )

    # response.text should be a JSON string matching the schema.
    return schema_model.model_validate_json(response.text)


def part_from_bytes(*, data: bytes, mime_type: str) -> types.Part:
    return types.Part.from_bytes(data=data, mime_type=mime_type)


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(Exception),
)
async def upload_file(*, path: str):
    """Upload a media file to Gemini Files API and return the uploaded file handle.

    The returned object can be passed directly in `contents=[uploaded_file, ...]`.
    """
    return await _client.aio.files.upload(file=path)
