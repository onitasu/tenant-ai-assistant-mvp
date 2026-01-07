from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.entities import Conversation, Message, MessageReference, MessageRole
from app.services import faiss_service
from app.services.gemini_service import generate_structured


def _distance_to_relevance(distance: float) -> float:
    # FAISS (IndexFlatL2) returns smaller-is-better distances.
    # Convert to a bounded 0..1 score for UI.
    return 1.0 / (1.0 + float(distance))


@dataclass
class ChunkResult:
    page_id: str
    page_number: int
    search_query: str
    detail_description: str
    image_url: str
    relevance_score: float


@dataclass
class FAQSearchResult:
    id: str
    title: str
    search_query: str
    answer: str
    page_id: Optional[str]
    page_number: Optional[int]
    image_url: Optional[str]
    relevance_score: float


class QueryResult(BaseModel):
    search_query: str = Field(description="ベクトル検索用の短い検索クエリ（キーワード/短いフレーズ）")


class LLMAnswerResult(BaseModel):
    answer: str = Field(description="回答テキスト")
    referenced_pages: List[int] = Field(description="最も参照したページ番号のリスト（最大3件）")


async def create_query(user_input: str) -> str:
    prompt = (
        "以下のユーザー質問を、ベクトル検索用の検索クエリに変換してください。\n"
        "- 検索クエリは短いキーワード/短いフレーズにしてください\n"
        "- 質問の本質的な意図を捉えてください\n"
        "- 出力はJSONのみ（search_queryフィールド）\n"
        f"\nユーザー質問: {user_input}"
    )

    result = await generate_structured(
        model=settings.gemini_chat_model,
        contents=prompt,
        schema_model=QueryResult,
        config={"temperature": 0},
    )
    return result.search_query.strip()


async def search_faiss_db(user_query: str, top_k: int = 5) -> tuple[List[ChunkResult], List[FAQSearchResult]]:
    # Chunk index
    chunk_docs = faiss_service.similarity_search_with_score(
        dir_path=settings.chunk_faiss_dir,
        query=user_query,
        k=top_k,
    )

    chunk_results: List[ChunkResult] = []
    for doc, distance in chunk_docs:
        md = doc.metadata or {}
        chunk_results.append(
            ChunkResult(
                page_id=str(md.get("page_id")),
                page_number=int(md.get("page_number")),
                search_query=str(doc.page_content),
                detail_description=str(md.get("detail_description") or ""),
                image_url=str(md.get("image_url") or ""),
                relevance_score=_distance_to_relevance(distance),
            )
        )

    # FAQ index
    faq_docs = faiss_service.similarity_search_with_score(
        dir_path=settings.faq_faiss_dir,
        query=user_query,
        k=3,
    )

    faq_results: List[FAQSearchResult] = []
    for doc, distance in faq_docs:
        md = doc.metadata or {}
        faq_results.append(
            FAQSearchResult(
                id=str(md.get("faq_id")),
                title=str(md.get("title") or ""),
                search_query=str(doc.page_content),
                answer=str(md.get("answer") or ""),
                page_id=md.get("page_id"),
                page_number=md.get("page_number"),
                image_url=md.get("image_url"),
                relevance_score=_distance_to_relevance(distance),
            )
        )

    return chunk_results, faq_results


async def create_llm_answer(chunk_results: List[ChunkResult], user_input: str) -> LLMAnswerResult:
    context = "\n\n".join(
        [
            f"【ページ{r.page_number}】\n{r.detail_description}"
            for r in chunk_results
        ]
    )

    prompt = (
        "以下の参照資料を基に、ユーザーの質問に回答してください。\n\n"
        "## 参照資料\n"
        f"{context}\n\n"
        "## ユーザーの質問\n"
        f"{user_input}\n\n"
        "## 出力形式（JSON）\n"
        "{\n"
        '  "answer": "回答テキスト",\n'
        '  "referenced_pages": [1, 2, 3]\n'
        "}\n\n"
        "注意事項:\n"
        "- 確信度が低い場合は「確認が必要です」と明示してください\n"
        "- referenced_pages は根拠となるページ番号を最大3件までにしてください\n"
        "- 出力はJSONのみ（追加の説明文は禁止）\n"
    )

    return await generate_structured(
        model=settings.gemini_chat_model,
        contents=prompt,
        schema_model=LLMAnswerResult,
        config={"temperature": 0.2},
    )


async def _get_or_create_conversation(db: AsyncSession, session_id: str) -> Conversation:
    res = await db.execute(select(Conversation).where(Conversation.session_id == session_id))
    conv = res.scalar_one_or_none()
    if conv:
        return conv

    conv = Conversation(id=str(uuid4()), session_id=session_id)
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv


async def handle_chat(db: AsyncSession, *, user_input: str, session_id: str):
    # 1) Conversation
    conv = await _get_or_create_conversation(db, session_id)

    # 2) Store user message
    user_msg = Message(
        id=str(uuid4()),
        conversation_id=conv.id,
        role=MessageRole.user,
        content=user_input,
    )
    db.add(user_msg)
    await db.commit()

    # 3) Query rewrite
    user_query = await create_query(user_input)

    # 4) Vector search
    chunk_results, faq_results = await search_faiss_db(user_query)

    # 5) LLM answer
    llm = await create_llm_answer(chunk_results, user_input)

    # 6) Build references (map page_number -> chunk result)
    references = []
    for idx, page_number in enumerate(llm.referenced_pages[:3]):
        match = next((r for r in chunk_results if r.page_number == page_number), None)
        if not match:
            continue
        references.append(
            {
                "page_id": match.page_id,
                "page_number": match.page_number,
                "image_url": match.image_url,
                "relevance_score": match.relevance_score,
                "is_primary": idx == 0,
            }
        )

    # 7) Store assistant message + references
    assistant_msg = Message(
        id=str(uuid4()),
        conversation_id=conv.id,
        role=MessageRole.assistant,
        content=llm.answer,
    )
    db.add(assistant_msg)
    await db.flush()  # get assistant_msg.id

    for i, ref in enumerate(references):
        db.add(
            MessageReference(
                id=str(uuid4()),
                message_id=assistant_msg.id,
                page_id=ref["page_id"],
                relevance_score=ref["relevance_score"],
                is_primary=ref["is_primary"],
                display_order=i,
            )
        )

    await db.commit()

    return faq_results, llm.answer, references
