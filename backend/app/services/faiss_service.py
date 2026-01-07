from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Iterable, List, Tuple

from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS

from app.core.config import settings


def get_embeddings() -> OpenAIEmbeddings:
    # Uses the OpenAI API key from OPENAI_API_KEY env var (or settings.openai_api_key).
    # The LangChain docs show using OpenAIEmbeddings(model="text-embedding-3-large").
    return OpenAIEmbeddings(model=settings.openai_embedding_model)


def _index_exists(dir_path: Path) -> bool:
    return (dir_path / "index.faiss").exists() and (dir_path / "index.pkl").exists()


def delete_index(dir_path: Path) -> None:
    if dir_path.exists():
        shutil.rmtree(dir_path, ignore_errors=True)


def build_index_from_texts(*, dir_path: Path, texts: List[str], metadatas: List[dict[str, Any]]) -> None:
    if not texts:
        delete_index(dir_path)
        return

    embeddings = get_embeddings()
    vectorstore = FAISS.from_texts(texts=texts, embedding=embeddings, metadatas=metadatas)
    dir_path.mkdir(parents=True, exist_ok=True)
    vectorstore.save_local(str(dir_path))


def add_texts_to_index(*, dir_path: Path, texts: List[str], metadatas: List[dict[str, Any]]) -> None:
    if not texts:
        return

    embeddings = get_embeddings()
    if _index_exists(dir_path):
        vectorstore = FAISS.load_local(str(dir_path), embeddings, allow_dangerous_deserialization=True)
        vectorstore.add_texts(texts=texts, metadatas=metadatas)
        vectorstore.save_local(str(dir_path))
    else:
        build_index_from_texts(dir_path=dir_path, texts=texts, metadatas=metadatas)


def similarity_search_with_score(*, dir_path: Path, query: str, k: int) -> List[Tuple[Any, float]]:
    if not _index_exists(dir_path):
        return []
    embeddings = get_embeddings()
    vectorstore = FAISS.load_local(str(dir_path), embeddings, allow_dangerous_deserialization=True)
    return vectorstore.similarity_search_with_score(query, k=k)
