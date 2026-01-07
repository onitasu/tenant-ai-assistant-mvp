from __future__ import annotations

from typing import Optional, List

from pydantic import Field

from app.schemas.common import ORMBase


class FAQResponse(ORMBase):
    id: str
    title: str
    search_query: str
    answer: str
    page_id: Optional[str] = None
    display_order: int = 0
    created_at: Optional[str] = None


class FAQListResponse(ORMBase):
    items: List[FAQResponse]


class FAQCreateRequest(ORMBase):
    title: str
    search_query: str
    answer: str
    page_id: Optional[str] = None
    display_order: int = 0


class FAQUpdateRequest(ORMBase):
    title: Optional[str] = None
    search_query: Optional[str] = None
    answer: Optional[str] = None
    page_id: Optional[str] = None
    display_order: Optional[int] = None
