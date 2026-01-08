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


def _extract_page_to_pdf(doc: fitz.Document, page_index_zero_based: int, out_path: Path) -> bytes:
    """Extract a single page from a PDF and save it as a separate PDF file."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Create a new PDF with just this page
    new_doc = fitz.open()
    new_doc.insert_pdf(doc, from_page=page_index_zero_based, to_page=page_index_zero_based)
    pdf_bytes = new_doc.tobytes()
    out_path.write_bytes(pdf_bytes)
    new_doc.close()

    return pdf_bytes


def _render_page_to_png(doc: fitz.Document, page_index_zero_based: int, out_path: Path, dpi: int = 150) -> bytes:
    """Render a page to PNG for preview display."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    page = doc.load_page(page_index_zero_based)
    pix = page.get_pixmap(dpi=dpi)
    img_bytes = pix.tobytes("png")
    out_path.write_bytes(img_bytes)

    return img_bytes


def _build_static_url(relative_path_from_images_dir: Path) -> str:
    """Build a public URL for a file in the images directory."""
    rel = relative_path_from_images_dir.as_posix()
    return f"{settings.backend_public_url}/static/images/{rel}"



async def _extract_page_with_gemini(pdf_bytes: bytes, pdf_path: Path | None = None) -> PageExtraction:
    prompt = (
        "このPDFはテナント向けマニュアルの1ページです。以下の情報を漏れなく抽出してください。\n\n"
        "1. title（ページの見出し/タイトル）\n"
        "- ページ内で最も強調されているセクション番号とタイトルを抽出（例:「1-3 ロケーション＆アクセス」）\n"
        "- 複数のトピックがある場合は「 | 」で連結\n"
        "- ヘッダー/フッターの共通タイトルではなく、そのページ固有の内容を優先\n\n"
        "2. search_query（検索用クエリ）\n"
        "- ユーザーが検索窓に入力しそうな検索意図を含む短いフレーズを3〜5個\n"
        "- 文中の用語だけでなく、一般的な類義語も含める（例: 駐車場 -> パーキング/車でのアクセス）\n"
        "- 「〜はどこ」「〜の手続き」などアクションに基づいた表現を含める\n"
        "- 出力は1つの文字列にまとめ、「 | 」で連結\n\n"
        "3. page_text（本文テキスト）\n"
        "- ページのテキスト情報を可能な限り忠実に抽出\n"
        "- 表はMarkdown形式（|区切り）の表で構造化して出力\n"
        "- OCR由来の不要な記号の連続は読みやすさを損なわない範囲で整形\n\n"
        "4. img_description（図表の説明）\n"
        "- 図表やマップから読み取れる視覚的情報を、以下の見出しに従って構造化\n"
        "- 文字ラベル/部屋名/施設名/番号/矢印/記号/凡例は可能な限り正確に転記\n"
        "- 判読不能な部分は「判読不能」と明記し、推測しない\n\n"
        "img_descriptionの見出し:\n"
        "【種別】地図/フロアマップ/案内図/断面図/設備図/表/フロー図/写真/ロゴ/その他\n"
        "【全体概要】何を示している図か\n"
        "【エリア/施設】名称・番号を網羅（階数/ゾーン/部屋名を含む）\n"
        "【ランドマーク/設備】ELV/ESC/階段/トイレ/受付/給湯室/防災センター/AED/駐車場/出口/点検口など\n"
        "【方位/位置関係】方位記号があれば従う。なければ「方位不明」か「上部（北側と仮定）」のように明記。"
        "隣接関係を具体的に記述\n"
        "【動線/ルート】矢印やラインの経路を「開始地点 → 経由地点 → 到達地点」で手順化\n"
        "【凡例/色/記号】色/記号の意味を正確に説明\n"
        "【スペック/数値】寸法/耐荷重/天井高/電気容量/VAV分割数など\n"
        "【注意/禁止】注釈や禁止事項\n\n"
        "注意: 出力は指定されたJSONスキーマに必ず従ってください。"
    )

    # If the payload is large, you can use the Gemini Files API (file input).
    # Otherwise, inline bytes (Part.from_bytes) is sufficient for most page PDFs.
    use_files_api = False
    if pdf_path and pdf_path.exists():
        try:
            use_files_api = pdf_path.stat().st_size > 18 * 1024 * 1024
        except Exception:
            use_files_api = False

    if use_files_api:
        uploaded = await upload_file(path=str(pdf_path))
        contents = [uploaded, prompt]
    else:
        contents = [
            part_from_bytes(data=pdf_bytes, mime_type="application/pdf"),
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


from typing import AsyncGenerator


async def process_uploaded_document_with_progress(
    *,
    db: AsyncSession,
    document: Document,
    input_file_path: Path,
) -> AsyncGenerator[dict, None]:
    """Process an uploaded PDF/PPTX into pages, store in DB, and index in FAISS.

    Yields progress updates as dictionaries.
    """

    ensure_storage_dirs()

    # Mark processing
    document.status = DocumentStatus.processing
    await db.commit()

    yield {"status": "processing", "message": "ファイルを変換中..."}

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

    yield {"status": "processing", "message": f"全{total_pages}ページを処理します", "total_pages": total_pages, "current_page": 0}

    # Prepare metadata for FAISS chunk index
    texts: List[str] = []
    metadatas: List[dict] = []

    # Process pages in batches to balance speed and memory
    BATCH_SIZE = 3  # Process 3 pages in parallel

    async def process_single_page(page_index: int):
        """Process a single page and return page data."""
        page_number = page_index + 1

        # Save page as PDF (for Gemini processing)
        rel_pdf_path = Path("documents") / document.id / f"page_{page_number}.pdf"
        abs_pdf_path = settings.images_dir / rel_pdf_path
        pdf_bytes = await asyncio.to_thread(_extract_page_to_pdf, pdf_doc, page_index, abs_pdf_path)

        # Save page as PNG (for preview display)
        rel_png_path = Path("documents") / document.id / f"page_{page_number}.png"
        abs_png_path = settings.images_dir / rel_png_path
        await asyncio.to_thread(_render_page_to_png, pdf_doc, page_index, abs_png_path)

        # Use PNG URL for preview (image_url field)
        png_url = _build_static_url(rel_png_path)

        # Gemini OCR + document understanding (structured output) - uses PDF
        extraction = await _extract_page_with_gemini(pdf_bytes, abs_pdf_path)

        page_id = str(uuid4())
        return {
            "page_id": page_id,
            "page_number": page_number,
            "extraction": extraction,
            "png_url": png_url,
        }

    try:
        # Process in batches
        for batch_start in range(0, total_pages, BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, total_pages)
            batch_indices = list(range(batch_start, batch_end))

            yield {
                "status": "processing",
                "message": f"ページ {batch_start + 1}-{batch_end}/{total_pages} を処理中...",
                "total_pages": total_pages,
                "current_page": batch_end,
            }

            # Process batch in parallel
            tasks = [process_single_page(i) for i in batch_indices]
            results = await asyncio.gather(*tasks)

            # Store results
            for result in results:
                page = Page(
                    id=result["page_id"],
                    document_id=document.id,
                    page_number=result["page_number"],
                    title=result["extraction"].title,
                    page_text=result["extraction"].page_text,
                    search_query=result["extraction"].search_query,
                    img_description=result["extraction"].img_description,
                    image_url=result["png_url"],
                )
                db.add(page)

                texts.append(result["extraction"].search_query)
                metadatas.append({
                    "page_id": result["page_id"],
                    "document_id": document.id,
                    "page_number": result["page_number"],
                    "detail_description": _detail_description(result["extraction"]),
                    "image_url": result["png_url"],
                })

        await db.commit()

        yield {"status": "processing", "message": "インデックスを更新中...", "total_pages": total_pages, "current_page": total_pages}

        # Update FAISS index
        await asyncio.to_thread(
            faiss_service.add_texts_to_index,
            dir_path=settings.chunk_faiss_dir,
            texts=texts,
            metadatas=metadatas,
        )

        document.status = DocumentStatus.completed
        await db.commit()

    except Exception:
        await db.rollback()
        document.status = DocumentStatus.error
        await db.commit()
        raise

    finally:
        pdf_doc.close()
