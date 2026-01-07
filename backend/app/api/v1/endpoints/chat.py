from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.entities import Conversation, Message, MessageReference, Page, MessageRole
from app.schemas.chat import ChatRequest, ChatResponse, FAQResult, Reference
from app.schemas.conversations import ConversationResponse, MessageResponse
from app.services.chat_service import handle_chat

router = APIRouter()


@router.post("", response_model=ChatResponse)
async def post_chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    faq_results, answer, references = await handle_chat(db, user_input=req.query, session_id=req.session_id)

    return ChatResponse(
        faq_results=[
            FAQResult(
                id=r.id,
                title=r.title,
                search_query=r.search_query,
                answer=r.answer,
                page_id=r.page_id,
                page_number=r.page_number,
                image_url=r.image_url,
                relevance_score=r.relevance_score,
            )
            for r in faq_results
        ],
        answer=answer,
        references=[Reference(**ref) for ref in references],
    )


@router.get("/conversations/{session_id}", response_model=ConversationResponse)
async def get_conversation(session_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Conversation).where(Conversation.session_id == session_id))
    conv = res.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msg_res = await db.execute(
        select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at.asc())
    )
    messages = list(msg_res.scalars().all())

    out_messages: list[MessageResponse] = []
    for m in messages:
        refs_out: list[Reference] = []
        if m.role == MessageRole.assistant:
            refs = await db.execute(
                select(MessageReference, Page)
                .join(Page, MessageReference.page_id == Page.id)
                .where(MessageReference.message_id == m.id)
                .order_by(MessageReference.display_order.asc())
            )
            for ref, page in refs.all():
                refs_out.append(
                    Reference(
                        page_id=page.id,
                        page_number=page.page_number,
                        image_url=page.image_url or "",
                        relevance_score=ref.relevance_score or 0.0,
                        is_primary=bool(ref.is_primary),
                    )
                )

        out_messages.append(
            MessageResponse(
                id=m.id,
                role=m.role.value if hasattr(m.role, "value") else str(m.role),
                content=m.content,
                created_at=m.created_at,
                references=refs_out,
            )
        )

    return ConversationResponse(session_id=session_id, messages=out_messages)
