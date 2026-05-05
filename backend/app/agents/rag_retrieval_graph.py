from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from langchain_core.documents import Document
from langgraph.graph import END, START, StateGraph

from app.agents.state import ChatState
from app.agents.system_prompts import QA_QUERY_REWRITER_SYSTEM_PROMPT
from app.core.config import get_settings
from app.services.llm_runtime_service import LLMRuntimeService
from app.services.qdrant_service import QdrantService

QA_QUERY_REWRITER_AGENT_KEY = "qa-query-rewriter"
QA_QUERY_REWRITER_AGENT_NAME = "QAQueryRewriterAgent"
QA_QUERY_REWRITER_AGENT_DESCRIPTION = (
    "Формирует несколько коротких поисковых вариантов вопроса для QA RAG без добавления "
    "новых фактов."
)
QA_QUERY_REWRITER_AGENT_ALIASES: tuple[str, ...] = ()

_ATTACHMENT_SOURCE_TYPES = {"attachment_text", "attachment_image_alt_text"}
_CROSS_TASK_CONTEXT_SOURCE_TYPES = {
    "task_content",
    "attachment_text",
    "attachment_image_alt_text",
}
_MAX_QUERY_VARIANTS = 5
_MIN_QUERY_VARIANTS = 1
_DEFAULT_CANDIDATE_MULTIPLIER = 4
_MAX_RERANKED_DIAGNOSTICS = 12
_TOKEN_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё_]+")


class RagRetrievalState(ChatState, total=False):
    db: Any
    actor_user_id: str | None
    task_id: str | None
    project_id: str | None
    task_title: str
    task_status: str
    task_content: str
    task_tags: list[str]
    question: str
    retrieval_limit: int
    rewrite_system_prompt: str
    rewrite_user_prompt: str
    rewrite_payload: dict[str, object] | None
    query_rewriter_ok: bool
    query_rewriter_error_message: str | None
    query_rewriter_provider_kind: str | None
    query_rewriter_model: str | None
    retrieval_queries: list[str]
    retrieval_keywords: list[str]
    candidate_hits: list[dict[str, object]]
    reranked_hits: list[dict[str, object]]
    rag_snippets: list[str]
    rag_chunk_ids: list[str]
    attachment_filenames: list[str]
    cross_task_snippets: list[str]
    cross_task_chunk_ids: list[str]
    cross_task_ids: list[str]
    cross_task_sources: list[dict[str, str]]
    rag_context_scope: str
    reranked_chunks: list[dict[str, object]]


def _extract_json_payload(raw_text: str) -> dict[str, object] | None:
    text = raw_text.strip()
    if not text:
        return None
    candidates = [text]
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match is not None:
        candidates.append(match.group(0))
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _normalize_space(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _unique_limited(values: list[object], *, limit: int) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _normalize_space(value)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _tokens(value: object) -> set[str]:
    text = str(value or "").casefold().replace("ё", "е")
    return {token for token in _TOKEN_RE.findall(text) if len(token) > 2 and not token.isdigit()}


def _document_id(document: Document, fallback: str) -> str:
    metadata = document.metadata or {}
    return str(metadata.get("chunk_id") or fallback)


def _is_attachment_document(document: Document) -> bool:
    metadata = document.metadata or {}
    source_type = str(metadata.get("source_type") or "").strip()
    chunk_kind = str(metadata.get("chunk_kind") or "").strip()
    return source_type in _ATTACHMENT_SOURCE_TYPES or chunk_kind in _ATTACHMENT_SOURCE_TYPES


def _is_cross_task_context_document(document: Document) -> bool:
    metadata = document.metadata or {}
    source_type = str(metadata.get("source_type") or "").strip()
    chunk_kind = str(metadata.get("chunk_kind") or "").strip()
    return (
        source_type in _CROSS_TASK_CONTEXT_SOURCE_TYPES
        or chunk_kind in _CROSS_TASK_CONTEXT_SOURCE_TYPES
    )


def _format_cross_task_document(document: Document) -> tuple[str, dict[str, str]] | None:
    content = document.page_content.strip()
    if not content:
        return None

    metadata = document.metadata or {}
    source = {
        "task_id": str(metadata.get("task_id") or "").strip(),
        "task_title": str(metadata.get("task_title") or "").strip(),
        "task_status": str(metadata.get("status") or metadata.get("task_status") or "").strip(),
        "source_type": str(metadata.get("source_type") or "").strip(),
        "chunk_id": str(metadata.get("chunk_id") or "").strip(),
    }
    source_text = (
        f"Задача: {source['task_title'] or source['task_id'] or 'неизвестно'} "
        f"(id: {source['task_id'] or 'нет'}, статус: {source['task_status'] or 'нет'}, "
        f"source_type: {source['source_type'] or 'нет'}, chunk_id: {source['chunk_id'] or 'нет'})"
    )
    return f"{source_text}\n{content}", source


def _resolve_rag_context_scope(*, has_attachments: bool, has_cross_task: bool) -> str:
    if has_attachments and has_cross_task:
        return "attachments+cross_task"
    if has_attachments:
        return "attachments"
    if has_cross_task:
        return "cross_task"
    return "none"


def _prepare_rewrite_prompt(state: RagRetrievalState) -> RagRetrievalState:
    task_content = _normalize_space(state.get("task_content", ""))[:1200]
    task_tags = ", ".join(str(tag) for tag in list(state.get("task_tags", [])) if str(tag))
    question = _normalize_space(state.get("question", ""))
    return {
        "rewrite_system_prompt": QA_QUERY_REWRITER_SYSTEM_PROMPT,
        "rewrite_user_prompt": (
            f"Вопрос пользователя:\n{question}\n\n"
            f"Название задачи: {state.get('task_title', '')}\n"
            f"Статус задачи: {state.get('task_status', '')}\n"
            f"Теги задачи: {task_tags or 'нет'}\n"
            f"Краткое описание задачи:\n{task_content or 'нет'}"
        ),
    }


async def _invoke_query_rewriter(state: RagRetrievalState) -> RagRetrievalState:
    db = state.get("db")
    if db is None:
        return {
            "query_rewriter_ok": False,
            "query_rewriter_error_message": None,
            "query_rewriter_provider_kind": None,
            "query_rewriter_model": None,
            "rewrite_payload": None,
        }

    try:
        result = await LLMRuntimeService.invoke_chat(
            db,
            agent_key=QA_QUERY_REWRITER_AGENT_KEY,
            actor_user_id=state.get("actor_user_id"),
            task_id=state.get("task_id"),
            project_id=state.get("project_id"),
            system_prompt=str(state.get("rewrite_system_prompt", "")),
            user_prompt=str(state.get("rewrite_user_prompt", "")),
            prompt_key=QA_QUERY_REWRITER_AGENT_KEY,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "query_rewriter_ok": False,
            "query_rewriter_error_message": str(exc),
            "query_rewriter_provider_kind": None,
            "query_rewriter_model": None,
            "rewrite_payload": None,
        }
    return {
        "query_rewriter_ok": bool(result.ok),
        "query_rewriter_error_message": result.error_message,
        "query_rewriter_provider_kind": result.provider_kind,
        "query_rewriter_model": result.model,
        "rewrite_payload": (
            _extract_json_payload(result.text or "") if result.ok and result.text else None
        ),
    }


def _normalize_query_variants(state: RagRetrievalState) -> RagRetrievalState:
    question = _normalize_space(state.get("question", ""))
    payload = state.get("rewrite_payload") if state.get("query_rewriter_ok") else None
    raw_queries: list[object] = [question]
    raw_keywords: list[object] = []
    if isinstance(payload, dict):
        queries = payload.get("queries")
        keywords = payload.get("keywords")
        if isinstance(queries, list):
            raw_queries.extend(queries)
        if isinstance(keywords, list):
            raw_keywords.extend(keywords)

    queries = _unique_limited(raw_queries, limit=_MAX_QUERY_VARIANTS)
    if len(queries) < _MIN_QUERY_VARIANTS and question:
        queries = [question]
    keywords = _unique_limited(raw_keywords, limit=12)
    if not keywords:
        keywords = sorted(_tokens(" ".join(queries)))[:12]
    return {
        "retrieval_queries": queries,
        "retrieval_keywords": keywords,
    }


async def _retrieve_candidates(state: RagRetrievalState) -> RagRetrievalState:
    task_id = _normalize_space(state.get("task_id"))
    project_id = _normalize_space(state.get("project_id"))
    queries = list(state.get("retrieval_queries", []))
    retrieval_limit = max(1, int(state.get("retrieval_limit", 5)))
    candidate_limit = max(retrieval_limit * _DEFAULT_CANDIDATE_MULTIPLIER, 12)
    hits: list[dict[str, object]] = []

    for query in queries:
        if task_id:
            attachment_hits = await QdrantService.probe_task_knowledge_chunks(
                task_id=task_id,
                query_text=query,
                limit=candidate_limit,
                include_source_types=sorted(_ATTACHMENT_SOURCE_TYPES),
            )
            if not attachment_hits:
                attachment_hits = [
                    {"document": document, "score": 1.0}
                    for document in await QdrantService.search_task_knowledge(
                        task_id=task_id,
                        query_text=query,
                        limit=retrieval_limit,
                        include_source_types=sorted(_ATTACHMENT_SOURCE_TYPES),
                    )
                ]
            for hit in attachment_hits:
                hits.append({**hit, "scope": "current_task_attachment", "matched_query": query})
        if project_id:
            cross_task_hits = await QdrantService.probe_project_task_knowledge_chunks(
                project_id=project_id,
                query_text=query,
                exclude_task_id=task_id or None,
                limit=candidate_limit,
                include_source_types=sorted(_CROSS_TASK_CONTEXT_SOURCE_TYPES),
            )
            if not cross_task_hits:
                cross_task_hits = [
                    {"document": document, "score": 1.0}
                    for document in await QdrantService.search_project_task_knowledge(
                        project_id=project_id,
                        query_text=query,
                        exclude_task_id=task_id or None,
                        limit=retrieval_limit,
                        include_source_types=sorted(_CROSS_TASK_CONTEXT_SOURCE_TYPES),
                    )
                ]
            for hit in cross_task_hits:
                hits.append({**hit, "scope": "cross_task", "matched_query": query})

    return {"candidate_hits": hits}


def _score_hit(
    hit: dict[str, object],
    *,
    query_tokens: set[str],
    keyword_tokens: set[str],
    task_title_tokens: set[str],
    task_tag_tokens: set[str],
    threshold: float,
) -> dict[str, object]:
    document = hit["document"]
    if not isinstance(document, Document):
        return {**hit, "rerank_score": 0.0, "rerank_reasons": ["invalid_document"]}

    content = document.page_content.strip()
    metadata = document.metadata or {}
    score = float(hit.get("score") or 0.0)
    content_tokens = _tokens(content)
    metadata_tokens = _tokens(
        " ".join(
            str(metadata.get(key) or "")
            for key in ("task_title", "source_type", "chunk_kind", "filename")
        )
    )
    all_tokens = content_tokens | metadata_tokens

    query_overlap = len(query_tokens & all_tokens) / max(len(query_tokens), 1)
    keyword_overlap = len(keyword_tokens & all_tokens) / max(len(keyword_tokens), 1)
    title_overlap = len(task_title_tokens & all_tokens) / max(len(task_title_tokens), 1)
    tag_overlap = len(task_tag_tokens & all_tokens) / max(len(task_tag_tokens), 1)

    reasons: list[str] = []
    rerank_score = score
    if query_overlap:
        rerank_score += query_overlap * 0.22
        reasons.append("query_overlap")
    if keyword_overlap:
        rerank_score += keyword_overlap * 0.18
        reasons.append("keyword_overlap")
    if title_overlap:
        rerank_score += title_overlap * 0.08
        reasons.append("title_overlap")
    if tag_overlap:
        rerank_score += tag_overlap * 0.06
        reasons.append("tag_overlap")
    if _is_attachment_document(document):
        rerank_score += 0.04
        reasons.append("attachment_boost")
    if not content:
        rerank_score -= 1.0
        reasons.append("empty_content")
    elif len(content) < 40:
        rerank_score -= 0.08
        reasons.append("short_content_penalty")
    if score < threshold:
        rerank_score -= (threshold - score) * 0.5
        reasons.append("below_threshold_penalty")

    return {
        **hit,
        "rerank_score": round(max(rerank_score, 0.0), 4),
        "rerank_reasons": reasons,
    }


def _rerank_candidates(state: RagRetrievalState) -> RagRetrievalState:
    threshold = float(get_settings().RAG_CHUNK_MIN_SCORE)
    query_tokens = _tokens(" ".join(list(state.get("retrieval_queries", []))))
    keyword_tokens = _tokens(" ".join(list(state.get("retrieval_keywords", []))))
    task_title_tokens = _tokens(state.get("task_title", ""))
    task_tag_tokens = _tokens(" ".join(list(state.get("task_tags", []))))

    deduped: dict[str, dict[str, object]] = {}
    for index, hit in enumerate(list(state.get("candidate_hits", []))):
        document = hit.get("document")
        if not isinstance(document, Document):
            continue
        ranked_hit = _score_hit(
            hit,
            query_tokens=query_tokens,
            keyword_tokens=keyword_tokens,
            task_title_tokens=task_title_tokens,
            task_tag_tokens=task_tag_tokens,
            threshold=threshold,
        )
        chunk_id = _document_id(document, f"candidate-{index}")
        existing = deduped.get(chunk_id)
        if existing is None or float(ranked_hit["rerank_score"]) > float(existing["rerank_score"]):
            deduped[chunk_id] = ranked_hit

    reranked = sorted(
        deduped.values(),
        key=lambda item: (float(item.get("rerank_score") or 0.0), float(item.get("score") or 0.0)),
        reverse=True,
    )
    return {"reranked_hits": reranked}


def _diagnostic_chunk(hit: dict[str, object], *, fallback_id: str) -> dict[str, object]:
    document = hit.get("document")
    metadata = dict(getattr(document, "metadata", {}) or {})
    return {
        "chunk_id": str(metadata.get("chunk_id") or fallback_id),
        "scope": str(hit.get("scope") or ""),
        "score": round(float(hit.get("score") or 0.0), 4),
        "rerank_score": round(float(hit.get("rerank_score") or 0.0), 4),
        "matched_query": str(hit.get("matched_query") or ""),
        "rerank_reasons": list(hit.get("rerank_reasons", [])),
        "task_id": str(metadata.get("task_id") or "") or None,
        "task_title": str(metadata.get("task_title") or "") or None,
        "source_type": str(metadata.get("source_type") or "") or None,
        "filename": str(metadata.get("filename") or "") or None,
    }


def _finalize_retrieval(state: RagRetrievalState) -> RagRetrievalState:
    threshold = float(get_settings().RAG_CHUNK_MIN_SCORE)
    retrieval_limit = max(1, int(state.get("retrieval_limit", 5)))
    task_id = _normalize_space(state.get("task_id"))

    attachment_documents: list[Document] = []
    cross_task_documents: list[Document] = []
    selected_cross_task_total = 0
    per_task_count: dict[str, int] = {}

    for hit in list(state.get("reranked_hits", [])):
        document = hit.get("document")
        if not isinstance(document, Document):
            continue
        if not document.page_content.strip():
            continue
        if float(hit.get("score") or 0.0) < threshold:
            continue

        scope = str(hit.get("scope") or "")
        if scope == "current_task_attachment" and _is_attachment_document(document):
            if len(attachment_documents) < retrieval_limit:
                attachment_documents.append(document)
            continue

        if scope == "cross_task":
            if not _is_cross_task_context_document(document):
                continue
            metadata = document.metadata or {}
            hit_task_id = str(metadata.get("task_id") or "").strip()
            if not hit_task_id or hit_task_id == task_id:
                continue
            if per_task_count.get(hit_task_id, 0) >= 2:
                continue
            if selected_cross_task_total >= retrieval_limit:
                continue
            per_task_count[hit_task_id] = per_task_count.get(hit_task_id, 0) + 1
            selected_cross_task_total += 1
            cross_task_documents.append(document)

    rag_snippets = [document.page_content for document in attachment_documents]
    rag_chunk_ids = [
        str(document.metadata.get("chunk_id"))
        for document in attachment_documents
        if document.metadata.get("chunk_id")
    ]
    attachment_filenames = [
        str(document.metadata.get("filename"))
        for document in attachment_documents
        if document.metadata.get("filename")
    ]

    cross_task_snippets: list[str] = []
    cross_task_sources: list[dict[str, str]] = []
    for document in cross_task_documents:
        formatted = _format_cross_task_document(document)
        if formatted is None:
            continue
        snippet, source = formatted
        cross_task_snippets.append(snippet)
        cross_task_sources.append(source)

    cross_task_chunk_ids = [
        source["chunk_id"] for source in cross_task_sources if source.get("chunk_id")
    ]
    cross_task_ids = list(
        dict.fromkeys(source["task_id"] for source in cross_task_sources if source.get("task_id"))
    )
    all_chunk_ids = [*rag_chunk_ids, *cross_task_chunk_ids]

    return {
        "rag_snippets": rag_snippets,
        "rag_chunk_ids": all_chunk_ids,
        "attachment_filenames": attachment_filenames,
        "cross_task_snippets": cross_task_snippets,
        "cross_task_chunk_ids": cross_task_chunk_ids,
        "cross_task_ids": cross_task_ids,
        "cross_task_sources": cross_task_sources,
        "rag_context_scope": _resolve_rag_context_scope(
            has_attachments=bool(rag_snippets),
            has_cross_task=bool(cross_task_snippets),
        ),
        "reranked_chunks": [
            _diagnostic_chunk(hit, fallback_id=f"reranked-{index}")
            for index, hit in enumerate(
                list(state.get("reranked_hits", []))[:_MAX_RERANKED_DIAGNOSTICS],
                start=1,
            )
        ],
    }


@lru_cache
def get_rag_retrieval_graph():
    graph = StateGraph(RagRetrievalState)
    graph.add_node("prepare_rewrite_prompt", _prepare_rewrite_prompt)
    graph.add_node("invoke_query_rewriter", _invoke_query_rewriter)
    graph.add_node("normalize_query_variants", _normalize_query_variants)
    graph.add_node("retrieve_candidates", _retrieve_candidates)
    graph.add_node("rerank_candidates", _rerank_candidates)
    graph.add_node("finalize_retrieval", _finalize_retrieval)
    graph.add_edge(START, "prepare_rewrite_prompt")
    graph.add_edge("prepare_rewrite_prompt", "invoke_query_rewriter")
    graph.add_edge("invoke_query_rewriter", "normalize_query_variants")
    graph.add_edge("normalize_query_variants", "retrieve_candidates")
    graph.add_edge("retrieve_candidates", "rerank_candidates")
    graph.add_edge("rerank_candidates", "finalize_retrieval")
    graph.add_edge("finalize_retrieval", END)
    return graph.compile()


async def run_rag_retrieval_graph(
    *,
    db: Any,
    actor_user_id: str | None,
    task_id: str | None,
    project_id: str | None,
    task_title: str,
    task_status: str,
    task_content: str,
    task_tags: list[str] | None = None,
    question: str,
    retrieval_limit: int,
) -> RagRetrievalState:
    state = await get_rag_retrieval_graph().ainvoke(
        {
            "db": db,
            "actor_user_id": actor_user_id,
            "task_id": task_id,
            "project_id": project_id,
            "task_title": task_title,
            "task_status": task_status,
            "task_content": task_content,
            "task_tags": task_tags or [],
            "question": question,
            "retrieval_limit": retrieval_limit,
        }
    )
    return {
        "query_rewriter_ok": bool(state.get("query_rewriter_ok", False))
        and state.get("rewrite_payload") is not None,
        "query_rewriter_error_message": state.get("query_rewriter_error_message"),
        "query_rewriter_provider_kind": state.get("query_rewriter_provider_kind"),
        "query_rewriter_model": state.get("query_rewriter_model"),
        "retrieval_queries": list(state.get("retrieval_queries", [])),
        "retrieval_keywords": list(state.get("retrieval_keywords", [])),
        "rag_snippets": list(state.get("rag_snippets", [])),
        "rag_chunk_ids": list(state.get("rag_chunk_ids", [])),
        "attachment_filenames": list(state.get("attachment_filenames", [])),
        "cross_task_snippets": list(state.get("cross_task_snippets", [])),
        "cross_task_chunk_ids": list(state.get("cross_task_chunk_ids", [])),
        "cross_task_ids": list(state.get("cross_task_ids", [])),
        "cross_task_sources": list(state.get("cross_task_sources", [])),
        "rag_context_scope": str(state.get("rag_context_scope", "none")),
        "reranked_chunks": list(state.get("reranked_chunks", [])),
    }
