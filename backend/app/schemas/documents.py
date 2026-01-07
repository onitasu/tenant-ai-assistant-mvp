from __future__ import annotations

from typing import Optional, List
from pydantic import Field

from app.schemas.common import ORMBase


class DocumentResponse(ORMBase):
    id: str
    title: str
    status: str
    total_pages: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DocumentListResponse(ORMBase):
    items: List[DocumentResponse]


class PageResponse(ORMBase):
    id: str
    document_id: str
    page_number: int
    title: Optional[str] = None
    page_text: Optional[str] = None
    search_query: Optional[str] = None
    img_description: Optional[str] = None
    image_url: Optional[str] = None
    created_at: Optional[str] = None


class PageListResponse(ORMBase):
    items: List[PageResponse]


class DocumentDetailResponse(DocumentResponse):
    file_type: str
    file_path: str
