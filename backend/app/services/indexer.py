from __future__ import annotations

import asyncio
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.entities import FAQ, Page
from app.services import faiss_service


def _page_detail_description(page: Page) -> str:
    parts: list[str] = []
    if page.title:
        parts.append(f"【タイトル】{page.title}")
    if page.page_text:
        parts.append(f"【本文テキスト】\n{page.page_text}")
    if page.img_description:
        parts.append(f"【図表/画像の説明】\n{page.img_description}")
    return "\n\n".join(parts).strip()


async def rebuild_chunk_index(db: AsyncSession) -> None:
    res = await db.execute(select(Page).order_by(Page.document_id, Page.page_number))
    pages: List[Page] = list(res.scalars().all())

    texts: List[str] = []
    metadatas: List[dict] = []
    for p in pages:
        if not p.search_query:
            continue
        texts.append(p.search_query)
        metadatas.append(
            {
                "page_id": p.id,
                "document_id": p.document_id,
                "page_number": p.page_number,
                "detail_description": _page_detail_description(p),
                "image_url": p.image_url or "",
            }
        )

    await asyncio.to_thread(
        faiss_service.build_index_from_texts,
        dir_path=settings.chunk_faiss_dir,
        texts=texts,
        metadatas=metadatas,
    )


async def rebuild_faq_index(db: AsyncSession) -> None:
    # Join FAQ -> Page (optional) for page_number / image_url
    from sqlalchemy import outerjoin

    stmt = select(FAQ, Page).select_from(outerjoin(FAQ, Page, FAQ.page_id == Page.id)).order_by(
        FAQ.display_order.asc(), FAQ.created_at.asc()
    )
    res = await db.execute(stmt)

    texts: List[str] = []
    metadatas: List[dict] = []

    for faq, page in res.all():
        texts.append(faq.search_query)
        metadatas.append(
            {
                "faq_id": faq.id,
                "title": faq.title,
                "answer": faq.answer,
                "page_id": faq.page_id,
                "page_number": page.page_number if page else None,
                "image_url": page.image_url if page else None,
            }
        )

    await asyncio.to_thread(
        faiss_service.build_index_from_texts,
        dir_path=settings.faq_faiss_dir,
        texts=texts,
        metadatas=metadatas,
    )
