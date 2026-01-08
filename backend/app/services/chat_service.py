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
MAX_PDF_PAGES = 2
PDF_TASK_TIMEOUT_SECONDS = 60
MAX_HISTORY_MESSAGES = 5


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


class LLMTextResult(BaseModel):
    """テキストのみ回答のスキーマ。image_useでPDF画像を使うかどうかをLLMが判定する。"""
    answer: str = Field(description="回答テキスト")
    referenced_pages: List[int] = Field(description="最も参照したページ番号のリスト（最大3件）")
    image_use: bool = Field(description="テキスト情報だけでは回答が不十分でPDF画像を確認する必要があるならtrue")


def _build_context(chunk_results: List[ChunkResult]) -> str:
    return "\n\n".join(
        [
            f"【ページ{r.page_number}】\n{r.detail_description}"
            for r in chunk_results
        ]
    )


def _build_conversation_history(messages: List[Message]) -> str:
    """会話履歴をプロンプト用のテキストに変換"""
    if not messages:
        return ""

    history_lines = []
    for msg in messages:
        role_label = "ユーザー" if msg.role == MessageRole.user else "アシスタント"
        history_lines.append(f"{role_label}: {msg.content}")

    return "\n".join(history_lines)


def _png_url_to_pdf_path(png_url: str) -> Optional[Path]:
    """Convert a PNG preview URL to the corresponding PDF file path for Gemini processing.

    image_url stores PNG URL (for preview), but we need PDF file (for Gemini).
    Example: .../page_1.png -> .../page_1.pdf
    """
    if not png_url:
        return None
    try:
        parsed = urlparse(png_url)
    except Exception:
        return None
    marker = "/static/images/"
    if marker not in parsed.path:
        return None
    rel = parsed.path.split(marker, 1)[1].lstrip("/")
    if not rel:
        return None

    # Convert .png to .pdf
    if rel.endswith(".png"):
        rel = rel[:-4] + ".pdf"

    base = settings.images_dir.resolve()
    candidate = (settings.images_dir / Path(rel)).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    return candidate


async def _read_pdf_bytes(path: Path) -> Optional[bytes]:
    try:
        return await asyncio.to_thread(path.read_bytes)
    except (FileNotFoundError, OSError):
        return None


async def _build_pdf_parts(
    chunk_results: List[ChunkResult],
    max_pages: int = MAX_PDF_PAGES,
) -> tuple[List[object], List[int]]:
    """関連度順にPDFパーツを構築。実際に追加されたページ番号も返す。"""
    parts: List[object] = []
    seen_pages: set[int] = set()
    added = 0
    added_pages: List[int] = []

    for r in chunk_results:
        if r.page_number in seen_pages:
            continue
        seen_pages.add(r.page_number)
        path = _png_url_to_pdf_path(r.image_url)
        if not path:
            logger.warning(f"DEBUG pdf: page {r.page_number} - invalid path from url={r.image_url}")
            continue
        pdf_bytes = await _read_pdf_bytes(path)
        if not pdf_bytes:
            logger.warning(f"DEBUG pdf: page {r.page_number} - failed to read {path}")
            continue
        parts.append(f"ページ{r.page_number}のPDF")
        parts.append(part_from_bytes(data=pdf_bytes, mime_type="application/pdf"))
        added += 1
        added_pages.append(r.page_number)
        if added >= max_pages:
            break
    logger.info(f"DEBUG pdf: sent pages={added_pages}")
    return parts, added_pages


def _swallow_task_error(task: asyncio.Task) -> None:
    try:
        task.exception()
    except asyncio.CancelledError:
        pass
    except Exception:
        pass


async def _get_recent_messages(
    db: AsyncSession, conversation_id: str, limit: int = MAX_HISTORY_MESSAGES
) -> List[Message]:
    """指定した会話の直近N件のメッセージを取得（古い順）"""
    res = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    messages = list(res.scalars().all())
    # 古い順に並べ替え
    messages.reverse()
    return messages


async def create_query(user_input: str, conversation_history: str = "") -> str:
    """会話履歴を考慮してベクトル検索用クエリを生成"""

    history_section = ""
    if conversation_history:
        history_section = (
            "## 直近の会話履歴\n"
            f"{conversation_history}\n\n"
        )

    prompt = (
        "以下のユーザー質問を、ベクトル検索用の検索クエリに変換してください。\n\n"
        f"{history_section}"
        "## 現在のユーザー質問\n"
        f"{user_input}\n\n"
        "## 指示\n"
        "- 検索クエリは短いキーワード/短いフレーズにしてください（1行）\n"
        "- 重要語（施設名/設備名/手続き/料金/時間/条件/禁止事項/場所など）を漏れなく含める\n"
        "- 質問文の言い換えではなく、含まれる語を抽出して並べるイメージ\n"
        "- 会話履歴がある場合は、代名詞（それ、これ、あれ等）を具体的な名詞に解決してクエリに含める\n"
        "- **絶対に入力に存在しない単語を追加しないこと**（ビル名、地名、施設名など推測で補完しない）\n"
        "- 外部知識を使って情報を補完することは禁止\n"
        "- 出力はJSONのみ（search_queryフィールド）\n"
    )

    logger.info("[LLM PROMPT: create_query]")
    logger.info(f"model: {settings.gemini_chat_model}")
    logger.info(f"prompt:\n{prompt}")

    result = await generate_structured(
        model=settings.gemini_chat_model,
        contents=prompt,
        schema_model=QueryResult,
        config={"temperature": 0},
    )

    logger.info(f"[LLM RESPONSE: create_query] search_query={result.search_query}")

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
) -> LLMTextResult:
    context = _build_context(chunk_results)

    prompt = (
        "以下の参照資料を基に、ユーザーの質問に回答してください。\n\n"
        "## 参照資料（PDFから抽出したテキスト情報）\n"
        f"{context}\n\n"
        "## ユーザーの質問\n"
        f"{user_input}\n\n"
        "## 出力形式（JSON）\n"
        "{\n"
        '  "answer": "回答テキスト",\n'
        '  "referenced_pages": [1, 2, 3],\n'
        '  "image_use": false\n'
        "}\n\n"
        "## 注意事項\n"
        "- 回答は参照資料にある情報のみを使うこと（外部知識は禁止）\n"
        "- 資料に該当情報がない場合は「該当する情報が資料に見つかりませんでした」と答え、referenced_pages は空配列にすること\n"
        "- **信頼度が低い場合**は回答の中で「※この情報は確認が必要です」と明示してください\n"
        "- referenced_pages は根拠となるページ番号を最大3件までにしてください\n"
        "\n"
        "## image_use の判定基準\n"
        "- テキスト情報だけで十分に回答できる場合: image_use=false\n"
        "- 以下の場合は image_use=true:\n"
        "  - 図表・グラフ・レイアウトの確認が必要な場合\n"
        "  - テキスト情報だけでは回答の確信度が低い場合\n"
        "  - 視覚的な情報（地図、フロア図、手順図など）が重要な場合\n"
        "- 出力はJSONのみ（追加の説明文は禁止）\n"
    )

    logger.info("[LLM PROMPT: create_llm_answer_text_only]")
    logger.info(f"model: {settings.gemini_chat_model}")
    logger.info(f"prompt:\n{prompt}")

    result = await generate_structured(
        model=settings.gemini_chat_model,
        contents=prompt,
        schema_model=LLMTextResult,
        config={"temperature": 0.2},
    )

    logger.info(f"[LLM RESPONSE: create_llm_answer_text_only] image_use={result.image_use}, referenced_pages={result.referenced_pages}")

    return result


async def create_llm_answer_with_pdf(
    chunk_results: List[ChunkResult],
    user_input: str,
) -> tuple[LLMAnswerResult, List[int]]:
    """PDFを使った回答を生成。実際に使用したページ番号も返す。"""
    context = _build_context(chunk_results)
    pdf_parts, used_pages = await _build_pdf_parts(chunk_results)
    if not pdf_parts:
        raise RuntimeError("No valid PDF parts available for multimodal answer.")

    pages_description = "、".join([f"{p}ページ目" for p in used_pages])
    # referenced_pagesに使用可能なページ番号を明示
    available_pages_str = ", ".join([str(p) for p in used_pages])

    prompt = (
        "以下の参照資料と添付PDFを基に、ユーザーの質問に回答してください。\n\n"
        "## 参照資料（PDFから抽出したテキスト情報）\n"
        f"{context}\n\n"
        f"## 添付PDF（{pages_description}）\n"
        "上記の添付PDFを確認して回答に活用してください。\n\n"
        "## ユーザーの質問\n"
        f"{user_input}\n\n"
        "## 出力形式（JSON）\n"
        "{\n"
        '  "answer": "回答テキスト",\n'
        f'  "referenced_pages": [{available_pages_str}]\n'
        "}\n\n"
        "## 注意事項\n"
        "- 回答は参照資料と添付PDFにある情報のみを使うこと（外部知識は禁止）\n"
        "- 資料に該当情報がない場合は「該当する情報が資料に見つかりませんでした」と答え、referenced_pages は空配列にすること\n"
        "- **信頼度が低い場合**は回答の中で「※この情報は確認が必要です」と明示してください\n"
        f"- **回答の最後に**「詳細は添付資料の{pages_description}をご確認ください。」と補足を追加すること\n"
        f"- **重要**: referenced_pages には添付したページ番号 [{available_pages_str}] の中からのみ指定すること（他のページ番号は禁止）\n"
        "- 出力はJSONのみ（追加の説明文は禁止）\n"
    )

    logger.info("[LLM PROMPT: create_llm_answer_with_pdf]")
    logger.info(f"model: {settings.gemini_image_model}")
    logger.info(f"pdf_pages: {used_pages}")
    logger.info(f"prompt:\n{prompt}")

    contents = [*pdf_parts, prompt]
    result = await generate_structured(
        model=settings.gemini_image_model,
        contents=contents,
        schema_model=LLMAnswerResult,
        config={"temperature": 0.2},
    )

    logger.info(f"[LLM RESPONSE: create_llm_answer_with_pdf] referenced_pages={result.referenced_pages}")

    return result, used_pages


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


async def handle_prepare(db: AsyncSession, *, user_input: str, session_id: str):
    """クエリ生成とFAQ検索のみを行う（高速）"""
    # 1) Conversation
    conv = await _get_or_create_conversation(db, session_id)

    # 2) 過去の会話履歴を取得
    recent_messages = await _get_recent_messages(db, conv.id, limit=MAX_HISTORY_MESSAGES)
    conversation_history = _build_conversation_history(recent_messages)

    # 3) Query rewrite
    user_query = await create_query(user_input, conversation_history)

    # 4) FAQ search only (fast)
    faq_results = await search_faq_db(user_query)

    logger.info("=" * 60)
    logger.info("[PREPARE REQUEST]")
    logger.info(f"  user_input: {user_input}")
    logger.info(f"  prepared_query: {user_query}")
    logger.info(f"  faq_count: {len(faq_results)}")
    logger.info("=" * 60)

    return user_query, faq_results


async def handle_chat(db: AsyncSession, *, user_input: str, session_id: str, prepared_query: Optional[str] = None):
    # 1) Conversation
    conv = await _get_or_create_conversation(db, session_id)

    # 2) 過去の会話履歴を取得（直近5件）
    recent_messages = await _get_recent_messages(db, conv.id, limit=MAX_HISTORY_MESSAGES)
    conversation_history = _build_conversation_history(recent_messages)

    # 3) Store user message
    user_msg = Message(
        id=str(uuid4()),
        conversation_id=conv.id,
        role=MessageRole.user,
        content=user_input,
    )
    db.add(user_msg)
    await db.commit()

    # 4) Query rewrite（prepared_queryがあればスキップ）
    if prepared_query:
        user_query = prepared_query
        logger.info(f"[CHAT] Using prepared_query: {user_query}")
    else:
        user_query = await create_query(user_input, conversation_history)

    # 5) Vector search (chunks only, FAQs are handled by prepare)
    chunk_results = await search_chunk_db(user_query)

    # ========== ログ: 入力情報 ==========
    logger.info("=" * 60)
    logger.info("[CHAT REQUEST]")
    logger.info(f"  user_input: {user_input}")
    logger.info(f"  rewritten_query: {user_query}")
    logger.info(f"  search_results: pages={[r.page_number for r in chunk_results]}")
    logger.info("=" * 60)

    # 6) LLM answer (speculative parallel execution for better UX)
    # PDFモードをバックグラウンドで投機的に開始
    pdf_task = asyncio.create_task(create_llm_answer_with_pdf(chunk_results, user_input))
    pdf_task.add_done_callback(_swallow_task_error)

    answer_mode = "unknown"
    pdf_pages_used: List[int] = []

    try:
        text_llm = await create_llm_answer_text_only(chunk_results, user_input)
    except Exception as e:
        # テキストモードが失敗した場合、PDFモードにフォールバック
        logger.error(f"text_llm failed: {type(e).__name__}: {e}")
        try:
            llm, pdf_pages_used = await asyncio.wait_for(pdf_task, timeout=PDF_TASK_TIMEOUT_SECONDS)
            answer_mode = "PDF_MODE (fallback from text failure)"
        except Exception:
            pdf_task.cancel()
            answer_mode = "ERROR (both text and pdf failed)"
            logger.error("[CHAT RESPONSE] Both text and PDF modes failed")
            raise

    else:
        logger.info(f"[TEXT MODE RESULT] image_use={text_llm.image_use}, referenced_pages={text_llm.referenced_pages}")

        if not text_llm.image_use:
            # テキストのみで十分 → PDFタスクをキャンセル
            pdf_task.cancel()
            llm = LLMAnswerResult(
                answer=text_llm.answer,
                referenced_pages=text_llm.referenced_pages[:MAX_REFERENCED_PAGES],
            )
            answer_mode = "TEXT_MODE"
        else:
            # PDFを使って回答 → 投機的に開始したPDFタスクの結果を使用
            try:
                llm, pdf_pages_used = await asyncio.wait_for(pdf_task, timeout=PDF_TASK_TIMEOUT_SECONDS)
                answer_mode = "PDF_MODE"
            except Exception as e:
                logger.error(f"pdf_task failed: {type(e).__name__}: {e}")
                # PDFモードが失敗した場合はテキスト回答にフォールバック
                llm = LLMAnswerResult(
                    answer=text_llm.answer,
                    referenced_pages=text_llm.referenced_pages[:MAX_REFERENCED_PAGES],
                )
                answer_mode = "TEXT_MODE (fallback from pdf failure)"

    # ========== ログ: 出力情報 ==========
    logger.info("=" * 60)
    logger.info("[CHAT RESPONSE]")
    logger.info(f"  mode: {answer_mode}")
    if "PDF" in answer_mode:
        logger.info(f"  pdf_pages_used: {pdf_pages_used}")
    logger.info(f"  referenced_pages: {llm.referenced_pages}")
    logger.info(f"  answer: {llm.answer[:200]}{'...' if len(llm.answer) > 200 else ''}")
    logger.info("=" * 60)

    # 7) Build references (map page_number -> chunk result)
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

    # 8) Store assistant message + references
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
