from __future__ import annotations

import json
from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.agents.state import RagIndexState


class RagPipelineState(RagIndexState, total=False):
    title: str
    content: str
    tags: list[str]
    attachments: list[dict[str, str]]
    validation_result: dict | None
    base_chunks: list[dict[str, object]]
    attachment_chunks: list[dict[str, object]]
    validation_chunks: list[dict[str, object]]


def _collect_base_chunks(state: RagPipelineState) -> RagPipelineState:
    chunks: list[dict[str, object]] = [
        {
            "chunk_id": f"{state['task_id']}:title",
            "chunk_kind": "title",
            "content": str(state.get("title", "")).strip(),
        },
        {
            "chunk_id": f"{state['task_id']}:content",
            "chunk_kind": "content",
            "content": str(state.get("content", "")).strip(),
        },
    ]
    tags = list(state.get("tags", []))
    if tags:
        chunks.append(
            {
                "chunk_id": f"{state['task_id']}:tags",
                "chunk_kind": "tags",
                "content": "Tags: " + ", ".join(tags),
            }
        )
    return {"base_chunks": chunks}


def _collect_attachment_chunks(state: RagPipelineState) -> RagPipelineState:
    attachments = list(state.get("attachments", []))
    return {
        "attachment_chunks": [
            {
                "chunk_id": f"{state['task_id']}:attachment:{index}",
                "chunk_kind": "attachment",
                "content": (
                    "Attachment "
                    f"{item.get('filename', 'attachment')}"
                    f" ({item.get('content_type', 'application/octet-stream')})"
                    f", stored as {item.get('basename', '')}"
                ).strip(),
            }
            for index, _ in enumerate(attachments, start=1)
            for item in [attachments[index - 1]]
        ]
    }


def _collect_validation_chunks(state: RagPipelineState) -> RagPipelineState:
    validation_result = state.get("validation_result")
    if not validation_result:
        return {"validation_chunks": []}

    verdict = str(validation_result.get("verdict", ""))
    issues = list(validation_result.get("issues", []))
    questions = list(validation_result.get("questions", []))
    validation_payload = {
        "verdict": verdict,
        "issues": issues,
        "questions": questions,
    }
    return {
        "validation_chunks": [
            {
                "chunk_id": f"{state['task_id']}:validation",
                "chunk_kind": "validation",
                "content": "Validation context: " + json.dumps(validation_payload, ensure_ascii=False),
            }
        ]
    }


def _finalize_rag_index(state: RagPipelineState) -> RagPipelineState:
    chunks = [
        *list(state.get("base_chunks", [])),
        *list(state.get("attachment_chunks", [])),
        *list(state.get("validation_chunks", [])),
    ]
    normalized_chunks = [chunk for chunk in chunks if str(chunk.get("content", "")).strip()]
    chunk_ids = [str(chunk["chunk_id"]) for chunk in normalized_chunks]
    return {
        "indexed": True,
        "chunk_ids": chunk_ids,
        "chunks": normalized_chunks,
    }


@lru_cache
def get_rag_pipeline_graph():
    graph = StateGraph(RagPipelineState)
    graph.add_node("collect_base_chunks", _collect_base_chunks)
    graph.add_node("collect_attachment_chunks", _collect_attachment_chunks)
    graph.add_node("collect_validation_chunks", _collect_validation_chunks)
    graph.add_node("finalize_rag_index", _finalize_rag_index)
    graph.add_edge(START, "collect_base_chunks")
    graph.add_edge("collect_base_chunks", "collect_attachment_chunks")
    graph.add_edge("collect_attachment_chunks", "collect_validation_chunks")
    graph.add_edge("collect_validation_chunks", "finalize_rag_index")
    graph.add_edge("finalize_rag_index", END)
    return graph.compile()


async def run_rag_pipeline(
    *,
    task_id: str,
    title: str,
    content: str,
    tags: list[str],
    attachments: list[dict[str, str]],
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
    result: RagIndexState = {
        "task_id": task_id,
        "indexed": bool(state.get("indexed", False)),
        "chunk_ids": list(state.get("chunk_ids", [])),
        "chunks": list(state.get("chunks", [])),
    }
    return result
