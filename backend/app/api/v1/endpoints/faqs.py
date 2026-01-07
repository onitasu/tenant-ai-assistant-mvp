from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.entities import FAQ
from app.schemas.faqs import FAQCreateRequest, FAQListResponse, FAQResponse, FAQUpdateRequest
from app.services.indexer import rebuild_faq_index

router = APIRouter()


@router.get("", response_model=FAQListResponse)
async def list_faqs(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(FAQ).order_by(FAQ.display_order.asc(), FAQ.created_at.asc()))
    faqs = list(res.scalars().all())
    return FAQListResponse(items=[FAQResponse.model_validate(f) for f in faqs])


@router.post("", response_model=FAQResponse, status_code=status.HTTP_201_CREATED)
async def create_faq(req: FAQCreateRequest, db: AsyncSession = Depends(get_db)):
    faq = FAQ(
        id=str(uuid4()),
        title=req.title,
        search_query=req.search_query,
        answer=req.answer,
        page_id=req.page_id,
        display_order=req.display_order,
    )
    db.add(faq)
    await db.commit()
    await db.refresh(faq)

    await rebuild_faq_index(db)

    return FAQResponse.model_validate(faq)


@router.put("/{faq_id}", response_model=FAQResponse)
async def update_faq(faq_id: str, req: FAQUpdateRequest, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(FAQ).where(FAQ.id == faq_id))
    faq = res.scalar_one_or_none()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found")

    if req.title is not None:
        faq.title = req.title
    if req.search_query is not None:
        faq.search_query = req.search_query
    if req.answer is not None:
        faq.answer = req.answer
    if req.page_id is not None:
        faq.page_id = req.page_id
    if req.display_order is not None:
        faq.display_order = req.display_order

    await db.commit()
    await db.refresh(faq)

    await rebuild_faq_index(db)

    return FAQResponse.model_validate(faq)


@router.delete("/{faq_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_faq(faq_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(FAQ).where(FAQ.id == faq_id))
    faq = res.scalar_one_or_none()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found")

    await db.delete(faq)
    await db.commit()

    await rebuild_faq_index(db)

    return None
