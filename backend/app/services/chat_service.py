from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.entities import Conversation, Message, MessageReference, MessageRole
from app.services import faiss_service
from app.services.gemini_service import generate_structured, part_from_bytes

logger = logging.getLogger("uvicorn.error")

MAX_REFERENCED_PAGES = 3
MAX_IMAGE_PAGES = 2
IMAGE_TASK_TIMEOUT_SECONDS = 60
NEED_IMAGE_TRIGGER_PHRASES = ("資料に記載がありません", "確認が必要です")


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


class LLMNeedImageResult(BaseModel):
    answer: str = Field(description="回答テキスト")
    referenced_pages: List[int] = Field(description="最も参照したページ番号のリスト（最大3件）")
    need_image: bool = Field(description="画像が必要ならtrue")
    required_pages: List[int] = Field(description="画像が必要なページ番号（最大3件）")


def _build_context(chunk_results: List[ChunkResult]) -> str:
    return "\n\n".join(
        [
            f"【ページ{r.page_number}】\n{r.detail_description}"
            for r in chunk_results
        ]
    )


def _image_url_to_path(image_url: str) -> Optional[Path]:
    if not image_url:
        return None
    try:
        parsed = urlparse(image_url)
    except Exception:
        return None
    marker = "/static/images/"
    if marker not in parsed.path:
        return None
    rel = parsed.path.split(marker, 1)[1].lstrip("/")
    if not rel:
        return None
    base = settings.images_dir.resolve()
    candidate = (settings.images_dir / Path(rel)).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    return candidate


async def _read_image_bytes(path: Path) -> Optional[bytes]:
    try:
        return await asyncio.to_thread(path.read_bytes)
    except (FileNotFoundError, OSError):
        return None


async def _build_image_parts(chunk_results: List[ChunkResult], max_pages: int = MAX_IMAGE_PAGES) -> List[object]:
    parts: List[object] = []
    seen_pages: set[int] = set()
    added = 0
    added_pages: List[int] = []
    for r in chunk_results:
        if r.page_number in seen_pages:
            continue
        seen_pages.add(r.page_number)
        path = _image_url_to_path(r.image_url)
        if not path:
            logger.warning(f"DEBUG image: page {r.page_number} - invalid path from url={r.image_url}")
            continue
        image_bytes = await _read_image_bytes(path)
        if not image_bytes:
            logger.warning(f"DEBUG image: page {r.page_number} - failed to read {path}")
            continue
        parts.append(f"ページ{r.page_number}の画像")
        parts.append(part_from_bytes(data=image_bytes, mime_type="image/png"))
        added += 1
        added_pages.append(r.page_number)
        if added >= max_pages:
            break
    logger.info(f"DEBUG image: sent pages={added_pages}")
    return parts


def _swallow_task_error(task: asyncio.Task) -> None:
    try:
        task.exception()
    except asyncio.CancelledError:
        pass
    except Exception:
        pass


def _should_use_image(text_llm: LLMNeedImageResult) -> bool:
    if not text_llm.referenced_pages:
        return True
    answer = text_llm.answer or ""
    return any(phrase in answer for phrase in NEED_IMAGE_TRIGGER_PHRASES)


async def create_query(user_input: str) -> str:
    prompt = (
        "以下のユーザー質問を、ベクトル検索用の検索クエリに変換してください。\n"
        "- 検索クエリは短いキーワード/短いフレーズにしてください（1行）\n"
        "- 重要語（施設名/設備名/手続き/料金/時間/条件/禁止事項/場所など）を漏れなく含める\n"
        "- 質問文の言い換えではなく、含まれる語を抽出して並べるイメージ\n"
        "- 推測で情報を足さない\n"
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


async def search_chunk_db(user_query: str, top_k: int = 5) -> List[ChunkResult]:
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

    return chunk_results


async def search_faq_db(user_query: str, top_k: int = 3) -> List[FAQSearchResult]:
    # FAQ index
    faq_docs = faiss_service.similarity_search_with_score(
        dir_path=settings.faq_faiss_dir,
        query=user_query,
        k=top_k,
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

    return faq_results


async def create_llm_answer_text_only(
    chunk_results: List[ChunkResult], user_input: str
) -> LLMNeedImageResult:
    context = _build_context(chunk_results)
    prompt = (
        "以下の参照資料を基に、ユーザーの質問に回答してください。\n\n"
        "## 参照資料\n"
        f"{context}\n\n"
        "## ユーザーの質問\n"
        f"{user_input}\n\n"
        "## 出力形式（JSON）\n"
        "{\n"
        '  "answer": "回答テキスト",\n'
        '  "referenced_pages": [1, 2, 3],\n'
        '  "need_image": false,\n'
        '  "required_pages": [1, 2, 3]\n'
        "}\n\n"
        "注意事項:\n"
        "- 回答は参照資料にある情報のみを使うこと（外部知識は禁止）\n"
        "- 資料に該当情報がない場合は「資料に記載がありません」と答え、referenced_pages は空配列にすること\n"
        "- need_image と required_pages はシステム側で判定するため、need_image=false、required_pages=[] に固定\n"
        "- 確信度が低い場合は「確認が必要です」と明示してください\n"
        "- referenced_pages は根拠となるページ番号を最大3件までにしてください\n"
        "- 出力はJSONのみ（追加の説明文は禁止）\n"
    )

    return await generate_structured(
        model=settings.gemini_chat_model,
        contents=prompt,
        schema_model=LLMNeedImageResult,
        config={"temperature": 0.2},
    )


async def create_llm_answer_with_images(
    chunk_results: List[ChunkResult], user_input: str
) -> LLMAnswerResult:
    context = _build_context(chunk_results)
    image_parts = await _build_image_parts(chunk_results)
    if not image_parts:
        raise RuntimeError("No valid image parts available for multimodal answer.")
    prompt = (
        "以下の参照資料とページ画像を基に、ユーザーの質問に回答してください。\n\n"
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
        "- 回答は参照資料と提供画像にある情報のみを使うこと（外部知識は禁止）\n"
        "- 資料に該当情報がない場合は「資料に記載がありません」と答え、referenced_pages は空配列にすること\n"
        "- 確信度が低い場合は「確認が必要です」と明示してください\n"
        "- referenced_pages は根拠となるページ番号を最大3件まで（提供したページのみ）\n"
        "- 出力はJSONのみ（追加の説明文は禁止）\n"
    )

    contents = [*image_parts, prompt]
    return await generate_structured(
        model=settings.gemini_image_model,
        contents=contents,
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
    chunk_results = await search_chunk_db(user_query)
    logger.info(f"DEBUG search: query='{user_query}', pages={[r.page_number for r in chunk_results]}")

    # 5) LLM answer (speculative image run + text-only decision)
    image_task = asyncio.create_task(create_llm_answer_with_images(chunk_results, user_input))
    image_task.add_done_callback(_swallow_task_error)

    try:
        text_llm = await create_llm_answer_text_only(chunk_results, user_input)
    except Exception:
        # If text-only fails, try to fall back to image result.
        try:
            llm = await asyncio.wait_for(image_task, timeout=IMAGE_TASK_TIMEOUT_SECONDS)
            logger.info("chat_answer_path=image_fallback_text_failed")
        except Exception:
            image_task.cancel()
            logger.info("chat_answer_path=error_text_and_image_failed")
            raise
    else:
        logger.info(f"DEBUG: answer='{text_llm.answer}', referenced_pages={text_llm.referenced_pages}")
        if not _should_use_image(text_llm):
            image_task.cancel()
            llm = LLMAnswerResult(
                answer=text_llm.answer,
                referenced_pages=text_llm.referenced_pages[:MAX_REFERENCED_PAGES],
            )
            logger.info("chat_answer_path=text_only")
        else:
            try:
                llm = await asyncio.wait_for(image_task, timeout=IMAGE_TASK_TIMEOUT_SECONDS)
                logger.info(f"DEBUG image_llm: answer='{llm.answer}', referenced_pages={llm.referenced_pages}")
                logger.info("chat_answer_path=image_speculative")
            except Exception as e:
                logger.error(f"image_task failed: {type(e).__name__}: {e}")
                llm = LLMAnswerResult(
                    answer=text_llm.answer,
                    referenced_pages=text_llm.referenced_pages[:MAX_REFERENCED_PAGES],
                )
                logger.info("chat_answer_path=text_fallback_image_failed")

    # 6) Build references (map page_number -> chunk result)
    references = []
    for idx, page_number in enumerate(llm.referenced_pages[:MAX_REFERENCED_PAGES]):
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

    return llm.answer, references


async def handle_related_faqs(db: AsyncSession, *, user_input: str, session_id: Optional[str] = None):
    user_query = await create_query(user_input)
    faq_results = await search_faq_db(user_query)
    return faq_results
