from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

import fitz  # PyMuPDF
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.entities import Document, DocumentStatus, Page
from app.services import faiss_service
from app.services.gemini_service import generate_structured, part_from_bytes, upload_file


class PageExtraction(BaseModel):
    title: Optional[str] = Field(default=None, description="ページの見出し/タイトル（分かる範囲）")
    search_query: str = Field(description="ベクトル検索用の短い検索クエリ（キーワード/短いフレーズ）")
    page_text: Optional[str] = Field(default=None, description="OCRで抽出した本文テキスト（可能な範囲で忠実に）")
    img_description: Optional[str] = Field(default=None, description="図表/地図/イラスト等の視覚要素の説明（読み取れる情報を具体的に）")


def ensure_storage_dirs() -> None:
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.images_dir.mkdir(parents=True, exist_ok=True)
    settings.faiss_dir.mkdir(parents=True, exist_ok=True)
    settings.tmp_dir.mkdir(parents=True, exist_ok=True)


def _soffice_convert_to_pdf(input_path: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)

    # LibreOffice headless convert
    # Example: soffice --headless --convert-to pdf --outdir /tmp file.pptx
    cmd = [
        "soffice",
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(out_dir),
        str(input_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    pdf_path = out_dir / (input_path.stem + ".pdf")
    if not pdf_path.exists():
        raise RuntimeError(f"PPTX->PDF conversion failed: {pdf_path} not found")
    return pdf_path


def _render_page_to_png(doc: fitz.Document, page_index_zero_based: int, out_path: Path, dpi: int = 200) -> bytes:
    page = doc.load_page(page_index_zero_based)
    pix = page.get_pixmap(dpi=dpi)
    img_bytes = pix.tobytes("png")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(img_bytes)
    return img_bytes


def _build_image_url(relative_path_from_images_dir: Path) -> str:
    # images_dir is served at /static/images (see FastAPI StaticFiles mount)
    rel = relative_path_from_images_dir.as_posix()
    return f"{settings.backend_public_url}/static/images/{rel}"



async def _extract_page_with_gemini(image_bytes: bytes, image_path: Path | None = None) -> PageExtraction:
    prompt = (
        "この画像はテナント向けマニュアルの1ページです。"
        "以下の情報を漏れなく抽出してください。\n"
        "1. ベクトル検索に使用する検索クエリ（ページ内容を表す日本語の短いキーワード/フレーズ）\n"
        "2. OCRで抽出した本文テキスト（可能な範囲で忠実に）\n"
        "3. 図表/地図/フロー図/注意書き/表など、視覚要素に含まれる情報の説明（読み取れる情報を具体的に）\n"
        "4. ページの見出し/タイトル（分かる範囲）\n"
        "\n"
        "注意: 出力は指定されたJSONスキーマに必ず従ってください。"
    )

    # If the payload is large, you can use the Gemini Files API (file input).
    # Otherwise, inline bytes (Part.from_bytes) is sufficient for most page images.
    use_files_api = False
    if image_path and image_path.exists():
        try:
            use_files_api = image_path.stat().st_size > 18 * 1024 * 1024
        except Exception:
            use_files_api = False

    if use_files_api:
        uploaded = await upload_file(path=str(image_path))
        contents = [uploaded, prompt]
    else:
        contents = [
            part_from_bytes(data=image_bytes, mime_type="image/png"),
            prompt,
        ]

    return await generate_structured(
        model=settings.gemini_chunk_model,
        contents=contents,
        schema_model=PageExtraction,
        config={
            # Keep extraction deterministic-ish
            "temperature": 0,
        },
    )


def _detail_description(ex: PageExtraction) -> str:
    parts: list[str] = []
    if ex.title:
        parts.append(f"【タイトル】{ex.title}")
    if ex.page_text:
        parts.append(f"【本文テキスト】\n{ex.page_text}")
    if ex.img_description:
        parts.append(f"【図表/画像の説明】\n{ex.img_description}")
    return "\n\n".join(parts).strip()


async def process_uploaded_document(
    *,
    db: AsyncSession,
    document: Document,
    input_file_path: Path,
) -> int:
    """Process an uploaded PDF/PPTX into pages, store in DB, and index in FAISS."""

    ensure_storage_dirs()

    # Mark processing
    document.status = DocumentStatus.processing
    await db.commit()

    # Convert PPTX -> PDF if needed
    file_type = document.file_type.lower()
    pdf_path = input_file_path
    if file_type in {"pptx", "ppt"}:
        pdf_path = await asyncio.to_thread(_soffice_convert_to_pdf, input_file_path, settings.tmp_dir)

    # Open PDF and iterate pages
    try:
        pdf_doc = fitz.open(str(pdf_path))
    except Exception:
        document.status = DocumentStatus.error
        await db.commit()
        raise

    total_pages = pdf_doc.page_count
    document.total_pages = total_pages
    await db.commit()

    # Prepare metadata for FAISS chunk index
    texts: List[str] = []
    metadatas: List[dict] = []

    try:
        for i in range(total_pages):
            page_number = i + 1

            # Save page image under storage/images/documents/{document_id}/page_{n}.png
            rel_image_path = Path("documents") / document.id / f"page_{page_number}.png"
            abs_image_path = settings.images_dir / rel_image_path
            image_bytes = await asyncio.to_thread(_render_page_to_png, pdf_doc, i, abs_image_path)

            image_url = _build_image_url(rel_image_path)

            # Gemini OCR + image understanding (structured output)
            extraction = await _extract_page_with_gemini(image_bytes, abs_image_path)

            page_id = str(uuid4())
            page = Page(
                id=page_id,
                document_id=document.id,
                page_number=page_number,
                title=extraction.title,
                page_text=extraction.page_text,
                search_query=extraction.search_query,
                img_description=extraction.img_description,
                image_url=image_url,
            )
            db.add(page)

            # Collect for FAISS
            texts.append(extraction.search_query)
            metadatas.append(
                {
                    "page_id": page_id,
                    "document_id": document.id,
                    "page_number": page_number,
                    "detail_description": _detail_description(extraction),
                    "image_url": image_url,
                }
            )

        await db.commit()

        # Update FAISS index
        await asyncio.to_thread(
            faiss_service.add_texts_to_index,
            dir_path=settings.chunk_faiss_dir,
            texts=texts,
            metadatas=metadatas,
        )

        document.status = DocumentStatus.completed
        await db.commit()

        return total_pages

    except Exception:
        await db.rollback()
        document.status = DocumentStatus.error
        await db.commit()
        raise

    finally:
        pdf_doc.close()