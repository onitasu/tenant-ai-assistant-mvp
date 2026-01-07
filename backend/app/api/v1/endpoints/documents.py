from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.entities import Document, Page
from app.schemas.documents import (
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentResponse,
    PageListResponse,
    PageResponse,
)
from app.services.document_processor import process_uploaded_document_with_progress, ensure_storage_dirs
from app.services.indexer import rebuild_chunk_index

router = APIRouter()


def _infer_file_type(filename: str) -> str:
    ext = filename.split(".")[-1].lower()
    return ext


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    db: AsyncSession = Depends(get_db),
    file: UploadFile = File(...),
    title: str = Form(default=""),
):
    """Upload document with SSE progress streaming."""
    ensure_storage_dirs()

    if not file.filename:
        raise HTTPException(status_code=400, detail="filename is required")

    file_type = _infer_file_type(file.filename)
    if file_type not in {"pdf", "pptx", "ppt"}:
        raise HTTPException(status_code=400, detail="Only PDF/PPTX are supported")

    document_id = str(uuid4())
    safe_title = title.strip() or Path(file.filename).stem

    upload_path = settings.uploads_dir / f"{document_id}.{file_type}"

    # Save upload
    content = await file.read()
    upload_path.write_bytes(content)

    doc = Document(
        id=document_id,
        title=safe_title,
        file_path=str(upload_path),
        file_type=file_type,
        total_pages=0,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    async def generate_progress():
        try:
            async for progress in process_uploaded_document_with_progress(
                db=db, document=doc, input_file_path=upload_path
            ):
                yield f"data: {json.dumps(progress)}\n\n"

            # Final success message
            await db.refresh(doc)
            yield f"data: {json.dumps({'status': 'completed', 'document': DocumentResponse.model_validate(doc).model_dump(mode='json')})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        generate_progress(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("", response_model=DocumentListResponse)
async def list_documents(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Document).order_by(Document.created_at.desc()))
    docs = list(res.scalars().all())
    return DocumentListResponse(items=[DocumentResponse.model_validate(d) for d in docs])


@router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document(document_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Document).where(Document.id == document_id))
    doc = res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentDetailResponse.model_validate(doc)


@router.get("/{document_id}/pages", response_model=PageListResponse)
async def list_pages(document_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(Page).where(Page.document_id == document_id).order_by(Page.page_number.asc())
    )
    pages = list(res.scalars().all())
    return PageListResponse(items=[PageResponse.model_validate(p) for p in pages])


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Document).where(Document.id == document_id))
    doc = res.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete associated files (best-effort)
    try:
        # upload file
        if doc.file_path and Path(doc.file_path).exists():
            Path(doc.file_path).unlink(missing_ok=True)
        # images folder
        images_dir = settings.images_dir / "documents" / doc.id
        if images_dir.exists():
            import shutil
            shutil.rmtree(images_dir, ignore_errors=True)
    except Exception:
        pass

    await db.delete(doc)
    await db.commit()

    # Rebuild chunk FAISS to remove deleted pages
    await rebuild_chunk_index(db)

    return None
