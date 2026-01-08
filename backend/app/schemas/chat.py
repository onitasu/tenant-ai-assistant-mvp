from __future__ import annotations

from typing import List, Optional

from pydantic import Field

from app.schemas.common import ORMBase


class ChatRequest(ORMBase):
    query: str = Field(..., description="ユーザー質問")
    session_id: str = Field(..., description="セッションID")
    prepared_query: Optional[str] = Field(None, description="事前に生成された検索クエリ（省略時は自動生成）")


class Reference(ORMBase):
    page_id: str
    page_number: int
    image_url: str
    relevance_score: float
    is_primary: bool = False


class FAQResult(ORMBase):
    id: str
    title: str
    search_query: str
    answer: str
    page_id: Optional[str] = None
    page_number: Optional[int] = None
    image_url: Optional[str] = None
    relevance_score: float


class PrepareResponse(ORMBase):
    prepared_query: str = Field(..., description="生成された検索クエリ")
    related_faqs: List[FAQResult] = []


class ChatResponse(ORMBase):
    answer: str
    references: List[Reference]
