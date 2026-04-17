from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.agents.state import RagIndexState


class RagPipelineState(RagIndexState, total=False):
    title: str
    content: str
    tags: list[str]
    attachments: list[dict[str, str]]
    validation_result: dict | None
    base_chunk_ids: list[str]
    attachment_chunk_ids: list[str]
    validation_chunk_ids: list[str]


def _collect_base_chunks(state: RagPipelineState) -> RagPipelineState:
    chunk_ids = [f"{state['task_id']}:title", f"{state['task_id']}:content"]
    if state.get("tags"):
        chunk_ids.append(f"{state['task_id']}:tags")
    return {"base_chunk_ids": chunk_ids}


def _collect_attachment_chunks(state: RagPipelineState) -> RagPipelineState:
    attachments = list(state.get("attachments", []))
    return {
        "attachment_chunk_ids": [
            f"{state['task_id']}:attachment:{index}"
            for index, _ in enumerate(attachments, start=1)
        ]
    }


def _collect_validation_chunks(state: RagPipelineState) -> RagPipelineState:
    if state.get("validation_result"):
        return {"validation_chunk_ids": [f"{state['task_id']}:validation"]}
    return {"validation_chunk_ids": []}


def _finalize_rag_index(state: RagPipelineState) -> RagPipelineState:
    chunk_ids = [
        *list(state.get("base_chunk_ids", [])),
        *list(state.get("attachment_chunk_ids", [])),
        *list(state.get("validation_chunk_ids", [])),
    ]
    return {
        "indexed": True,
        "chunk_ids": chunk_ids,
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
) -> list[str]:
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
    }
    return result["chunk_ids"]
