from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.state import RagIndexState
from app.core.config import get_settings
from app.services.graph_run_tracing import run_traced_graph, traced_node


class RagPipelineState(RagIndexState, total=False):
    title: str
    content: str
    tags: list[str]
    attachments: list[dict[str, Any]]
    task_sources: list[dict[str, Any]]
    attachment_sources: list[dict[str, Any]]


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _normalize_structured_text(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+$", "", line) for line in normalized.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _looks_structured_for_chunking(text: str) -> bool:
    return bool(
        re.search(r"(?m)^#{1,6}\s+\S", text)
        or re.search(r"(?m)^\s*[-*+]\s+\S", text)
        or re.search(r"(?m)^\s*\d+[.)]\s+\S", text)
        or re.search(r"(?m)^\s*\|.+\|\s*$", text)
        or "\n\n" in text
    )


def _is_heading(line: str) -> bool:
    return bool(re.match(r"^#{1,6}\s+\S", line.strip()))


def _is_list_line(line: str) -> bool:
    stripped = line.strip()
    return bool(re.match(r"^([-*+]|\d+[.)])\s+\S", stripped))


def _is_table_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2


def _split_structured_blocks(text: str) -> list[str]:
    normalized = _normalize_structured_text(text)
    if not normalized:
        return []

    blocks: list[str] = []
    buffer: list[str] = []
    current_heading = ""

    def flush_buffer() -> None:
        nonlocal buffer
        content = "\n".join(buffer).strip()
        buffer = []
        if not content:
            return
        if current_heading and not content.startswith(current_heading):
            content = f"{current_heading}\n{content}"
        blocks.append(content)

    lines = normalized.split("\n")
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            flush_buffer()
            index += 1
            continue

        if _is_heading(stripped):
            flush_buffer()
            current_heading = stripped
            index += 1
            continue

        if _is_table_line(stripped):
            flush_buffer()
            table_lines = [line]
            index += 1
            while index < len(lines) and _is_table_line(lines[index]):
                table_lines.append(lines[index])
                index += 1
            content = "\n".join(table_lines).strip()
            blocks.append(f"{current_heading}\n{content}".strip() if current_heading else content)
            continue

        if _is_list_line(stripped):
            flush_buffer()
            list_lines = [line]
            index += 1
            while index < len(lines) and (
                _is_list_line(lines[index])
                or (lines[index].startswith((" ", "\t")) and lines[index].strip())
            ):
                list_lines.append(lines[index])
                index += 1
            content = "\n".join(list_lines).strip()
            blocks.append(f"{current_heading}\n{content}".strip() if current_heading else content)
            continue

        buffer.append(line)
        index += 1

    flush_buffer()
    return [block for block in blocks if block.strip()]


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
        token_parts = [token[start : start + limit] for start in range(0, len(token), limit)] or [
            token
        ]
        for token_part in token_parts:
            separator_len = 1 if current_parts else 0
            next_len = current_len + separator_len + len(token_part)
            if current_parts and next_len > limit:
                chunks.append(" ".join(current_parts).strip())
                current_parts = []
                current_len = 0

            current_parts.append(token_part)
            current_len = len(token_part) if current_len == 0 else current_len + 1 + len(token_part)

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
    structured_text = _normalize_structured_text(text)
    if structured_text and _looks_structured_for_chunking(structured_text):
        structured_chunks = _split_structured_text_for_rag(
            structured_text,
            target_tokens=target_tokens,
            overlap_tokens=overlap_tokens,
            max_chars=max_chars,
        )
        if structured_chunks:
            return structured_chunks

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


def _split_structured_text_for_rag(
    text: str,
    *,
    target_tokens: int,
    overlap_tokens: int,
    max_chars: int | None = None,
) -> list[str]:
    blocks = _split_structured_blocks(text)
    if not blocks:
        return []

    target = max(target_tokens, 1)
    overlap = max(min(overlap_tokens, target - 1), 0)
    chunks: list[str] = []
    current_blocks: list[str] = []
    current_tokens = 0

    def flush_current() -> None:
        nonlocal current_blocks, current_tokens
        if not current_blocks:
            return
        chunk = "\n\n".join(current_blocks).strip()
        if max_chars is not None and len(chunk) > max_chars:
            chunks.extend(_split_text_by_max_chars(chunk, max_chars=max_chars))
        else:
            chunks.append(chunk)
        if overlap > 0:
            overlap_blocks: list[str] = []
            overlap_tokens_total = 0
            for block in reversed(current_blocks):
                block_tokens = len(_normalize_text(block).split())
                if overlap_blocks and overlap_tokens_total + block_tokens > overlap:
                    break
                overlap_blocks.insert(0, block)
                overlap_tokens_total += block_tokens
            current_blocks = overlap_blocks
            current_tokens = overlap_tokens_total
        else:
            current_blocks = []
            current_tokens = 0

    for block in blocks:
        block_tokens = len(_normalize_text(block).split())
        if block_tokens > target:
            flush_current()
            chunks.extend(
                split_text_for_rag(
                    _normalize_text(block),
                    target_tokens=target_tokens,
                    overlap_tokens=overlap_tokens,
                    max_chars=max_chars,
                )
            )
            current_blocks = []
            current_tokens = 0
            continue

        if current_blocks and current_tokens + block_tokens > target:
            flush_current()

        current_blocks.append(block)
        current_tokens += block_tokens

    flush_current()
    return [chunk for chunk in chunks if chunk.strip()]


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


def _finalize_rag_index(state: RagPipelineState) -> RagPipelineState:
    settings = get_settings()
    sources = [
        *list(state.get("task_sources", [])),
        *list(state.get("attachment_sources", [])),
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
    graph.add_node("collect_task_sources", traced_node("collect_task_sources", _collect_task_sources))
    graph.add_node("collect_attachment_sources", traced_node("collect_attachment_sources", _collect_attachment_sources))
    graph.add_node("finalize_rag_index", traced_node("finalize_rag_index", _finalize_rag_index))
    graph.add_edge(START, "collect_task_sources")
    graph.add_edge("collect_task_sources", "collect_attachment_sources")
    graph.add_edge("collect_attachment_sources", "finalize_rag_index")
    graph.add_edge("finalize_rag_index", END)
    return graph.compile()


async def run_rag_pipeline(
    *,
    db: Any | None = None,
    actor_user_id: str | None = None,
    task_id: str,
    project_id: str | None = None,
    title: str,
    content: str,
    tags: list[str],
    attachments: list[dict[str, Any]],
) -> RagIndexState:
    state = await run_traced_graph(
        graph_key="rag_pipeline",
        graph=get_rag_pipeline_graph(),
        source="rag_index",
        input_state=
        {
            "db": db,
            "actor_user_id": actor_user_id,
            "task_id": task_id,
            "project_id": project_id,
            "title": title,
            "content": content,
            "tags": tags,
            "attachments": attachments,
        }
    )
    return {
        "task_id": task_id,
        "indexed": bool(state.get("indexed", False)),
        "chunk_ids": list(state.get("chunk_ids", [])),
        "chunks": list(state.get("chunks", [])),
    }
