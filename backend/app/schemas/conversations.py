from __future__ import annotations

from typing import List, Optional

from pydantic import Field

from app.schemas.common import ORMBase
from app.schemas.chat import Reference


class MessageResponse(ORMBase):
    id: str
    role: str
    content: str
    created_at: Optional[str] = None
    references: List[Reference] = []


class ConversationResponse(ORMBase):
    session_id: str
    messages: List[MessageResponse]
