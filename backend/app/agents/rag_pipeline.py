from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.state import RagIndexState
from app.core.config import get_settings


class RagPipelineState(RagIndexState, total=False):
    title: str
    content: str
    tags: list[str]
    attachments: list[dict[str, Any]]
    validation_result: dict | None
    task_sources: list[dict[str, Any]]
    attachment_sources: list[dict[str, Any]]
    validation_sources: list[dict[str, Any]]


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _split_text_by_max_chars(text: str, *, max_chars: int) -> list[str]:
    limit = max(int(max_chars), 1)
    normalized = _normalize_text(text)
    if not normalized:
        return []
    if len(normalized) <= limit:
        return [normalized]

    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0
    for token in normalized.split(" "):
        token_parts = [
            token[start : start + limit]
            for start in range(0, len(token), limit)
        ] or [token]
        for token_part in token_parts:
            separator_len = 1 if current_parts else 0
            next_len = current_len + separator_len + len(token_part)
            if current_parts and next_len > limit:
                chunks.append(" ".join(current_parts).strip())
                current_parts = []
                current_len = 0

            current_parts.append(token_part)
            current_len = (
                len(token_part)
                if current_len == 0
                else current_len + 1 + len(token_part)
            )

    if current_parts:
        chunks.append(" ".join(current_parts).strip())
    return [chunk for chunk in chunks if chunk]


def split_text_for_rag(
    text: str,
    *,
    target_tokens: int,
    overlap_tokens: int,
    max_chars: int | None = None,
) -> list[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []

    tokens = normalized.split()
    target = max(target_tokens, 1)
    overlap = max(min(overlap_tokens, target - 1), 0)
    if len(tokens) <= target:
        if max_chars is None:
            return [normalized]
        return _split_text_by_max_chars(normalized, max_chars=max_chars)

    chunks: list[str] = []
    step = max(target - overlap, 1)
    start = 0
    while start < len(tokens):
        end = min(start + target, len(tokens))
        chunks.append(" ".join(tokens[start:end]).strip())
        if end >= len(tokens):
            break
        start += step
    if max_chars is None:
        return [chunk for chunk in chunks if chunk]

    limited_chunks: list[str] = []
    for chunk in chunks:
        limited_chunks.extend(_split_text_by_max_chars(chunk, max_chars=max_chars))
    return [chunk for chunk in limited_chunks if chunk]


def _source(
    *,
    chunk_kind: str,
    content: str,
    source_id: str,
    source_type: str,
    filename: str | None = None,
) -> dict[str, Any]:
    return {
        "chunk_kind": chunk_kind,
        "content": content,
        "filename": filename,
        "source_id": source_id,
        "source_type": source_type,
    }


def _collect_task_sources(state: RagPipelineState) -> RagPipelineState:
    task_id = str(state["task_id"])
    title = str(state.get("title", "")).strip()
    content = str(state.get("content", "")).strip()
    content_parts = []
    if title:
        content_parts.append(f"Название: {title}")
    if content:
        content_parts.append(f"Описание: {content}")

    sources = []
    if content_parts:
        sources.append(
            _source(
                chunk_kind="task_content",
                content="\n".join(content_parts),
                source_id=task_id,
                source_type="task_content",
            )
        )
    return {"task_sources": sources}


def _collect_attachment_sources(state: RagPipelineState) -> RagPipelineState:
    sources: list[dict[str, Any]] = []
    for index, item in enumerate(list(state.get("attachments", [])), start=1):
        filename = str(item.get("filename") or "attachment").strip()
        source_id = str(item.get("id") or index)

        alt_text = str(item.get("alt_text") or "").strip()
        extracted_text = str(item.get("extracted_text") or "").strip()
        is_image = bool(item.get("is_image"))

        if is_image and alt_text:
            sources.append(
                _source(
                    chunk_kind="attachment_image_alt_text",
                    content=f"Описание изображения: {alt_text}",
                    filename=filename,
                    source_id=source_id,
                    source_type="attachment_image_alt_text",
                )
            )
            continue

        if extracted_text:
            sources.append(
                _source(
                    chunk_kind="attachment_text",
                    content=f"Содержимое вложения:\n{extracted_text}",
                    filename=filename,
                    source_id=source_id,
                    source_type="attachment_text",
                )
            )
            continue

    return {"attachment_sources": sources}


def _validation_text_items(items: object, *, prefix: str) -> list[str]:
    if not isinstance(items, list):
        return []

    text_items: list[str] = []
    for item in items:
        if isinstance(item, dict):
            message = str(item.get("message", "")).strip()
            if not message:
                continue
            severity = str(item.get("severity", "")).strip()
            if severity:
                text_items.append(f"{prefix}: {message} ({severity})")
            else:
                text_items.append(f"{prefix}: {message}")
            continue

        text = str(item).strip()
        if text:
            text_items.append(f"{prefix}: {text}")

    return text_items


def _collect_validation_sources(state: RagPipelineState) -> RagPipelineState:
    validation_result = state.get("validation_result")
    if not validation_result:
        return {"validation_sources": []}

    validation_lines = [
        *_validation_text_items(validation_result.get("issues"), prefix="Замечание валидации"),
        *_validation_text_items(validation_result.get("questions"), prefix="Вопрос валидации"),
    ]
    if not validation_lines:
        return {"validation_sources": []}

    return {
        "validation_sources": [
            _source(
                chunk_kind="validation_result",
                content="\n".join(validation_lines),
                source_id=str(state["task_id"]),
                source_type="validation_result",
            )
        ]
    }


def _finalize_rag_index(state: RagPipelineState) -> RagPipelineState:
    settings = get_settings()
    sources = [
        *list(state.get("task_sources", [])),
        *list(state.get("attachment_sources", [])),
        *list(state.get("validation_sources", [])),
    ]

    chunks: list[dict[str, Any]] = []
    for source_doc in sources:
        split_chunks = split_text_for_rag(
            str(source_doc.get("content", "")),
            target_tokens=settings.RAG_CHUNK_TARGET_TOKENS,
            overlap_tokens=settings.RAG_CHUNK_OVERLAP_TOKENS,
            max_chars=settings.RAG_CHUNK_MAX_CHARS,
        )
        for chunk_index, content in enumerate(split_chunks):
            source_type = str(source_doc["source_type"])
            source_id = str(source_doc["source_id"])
            chunk = {
                "chunk_id": f"{state['task_id']}:{source_type}:{source_id}:{chunk_index}",
                "chunk_index": chunk_index,
                "chunk_kind": str(source_doc["chunk_kind"]),
                "content": content,
                "source_id": source_id,
                "source_total_chunks": len(split_chunks),
                "source_type": source_type,
            }
            filename = source_doc.get("filename")
            if filename:
                chunk["filename"] = str(filename)
            chunks.append(chunk)

    return {
        "indexed": True,
        "chunk_ids": [str(chunk["chunk_id"]) for chunk in chunks],
        "chunks": chunks,
    }


@lru_cache
def get_rag_pipeline_graph():
    graph = StateGraph(RagPipelineState)
    graph.add_node("collect_task_sources", _collect_task_sources)
    graph.add_node("collect_attachment_sources", _collect_attachment_sources)
    graph.add_node("collect_validation_sources", _collect_validation_sources)
    graph.add_node("finalize_rag_index", _finalize_rag_index)
    graph.add_edge(START, "collect_task_sources")
    graph.add_edge("collect_task_sources", "collect_attachment_sources")
    graph.add_edge("collect_attachment_sources", "collect_validation_sources")
    graph.add_edge("collect_validation_sources", "finalize_rag_index")
    graph.add_edge("finalize_rag_index", END)
    return graph.compile()


async def run_rag_pipeline(
    *,
    task_id: str,
    title: str,
    content: str,
    tags: list[str],
    attachments: list[dict[str, Any]],
    validation_result: dict | None,
) -> RagIndexState:
    state = await get_rag_pipeline_graph().ainvoke(
        {
            "task_id": task_id,
            "title": title,
            "content": content,
            "tags": tags,
            "attachments": attachments,
            "validation_result": validation_result,
        }
    )
    return {
        "task_id": task_id,
        "indexed": bool(state.get("indexed", False)),
        "chunk_ids": list(state.get("chunk_ids", [])),
        "chunks": list(state.get("chunks", [])),
    }
