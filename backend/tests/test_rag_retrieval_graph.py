from __future__ import annotations

from langchain_core.documents import Document

from app.agents.rag_retrieval_graph import run_rag_retrieval_graph
from app.services.llm_runtime_service import LLMInvocationResult


def _llm_result(text: str, *, ok: bool = True) -> LLMInvocationResult:
    return LLMInvocationResult(
        ok=ok,
        text=text if ok else None,
        provider_config_id="provider-1",
        provider_kind="openai",
        model="gpt-4o-mini",
        latency_ms=10,
        prompt_tokens=5,
        completion_tokens=5,
        total_tokens=10,
        estimated_cost_usd=None,
        error_message=None if ok else text,
    )


async def test_rag_retrieval_graph_uses_llm_query_variants_and_hybrid_rerank(
    monkeypatch,
) -> None:
    async def fake_invoke_chat(*args, **kwargs):  # type: ignore[no-untyped-def]
        assert kwargs["agent_key"] == "qa-query-rewriter"
        return _llm_result(
            '{"queries":["SLA вход email","SLA вход email","пароль SLA"],'
            '"keywords":["SLA","email"]}'
        )

    async def fake_probe_task_knowledge_chunks(**kwargs):  # type: ignore[no-untyped-def]
        if kwargs["query_text"] != "SLA вход email":
            return []
        return [
            {
                "document": Document(
                    page_content="General attachment without target words.",
                    metadata={
                        "chunk_id": "weak",
                        "source_type": "attachment_text",
                        "chunk_kind": "attachment_text",
                    },
                ),
                "score": 0.78,
            },
            {
                "document": Document(
                    page_content="SLA for email login is 15 minutes.",
                    metadata={
                        "chunk_id": "strong",
                        "source_type": "attachment_text",
                        "chunk_kind": "attachment_text",
                        "filename": "sla.txt",
                    },
                ),
                "score": 0.72,
            },
        ]

    monkeypatch.setattr(
        "app.services.llm_runtime_service.LLMRuntimeService.invoke_chat",
        fake_invoke_chat,
    )
    monkeypatch.setattr(
        "app.services.qdrant_service.QdrantService.probe_task_knowledge_chunks",
        fake_probe_task_knowledge_chunks,
    )

    result = await run_rag_retrieval_graph(
        db=object(),
        actor_user_id="user-1",
        task_id="task-1",
        project_id=None,
        task_title="SLA входа",
        task_status="ready_for_dev",
        task_content="Нужно уточнить SLA входа.",
        question="Какой SLA?",
        retrieval_limit=2,
    )

    assert result["query_rewriter_ok"] is True
    assert result["query_rewriter_provider_kind"] == "openai"
    assert result["query_rewriter_model"] == "gpt-4o-mini"
    assert result["retrieval_queries"] == ["Какой SLA?", "SLA вход email", "пароль SLA"]
    assert result["retrieval_keywords"] == ["SLA", "email"]
    assert result["rag_chunk_ids"] == ["strong", "weak"]
    assert result["attachment_filenames"] == ["sla.txt"]
    assert result["reranked_chunks"][0]["chunk_id"] == "strong"
    assert "keyword_overlap" in result["reranked_chunks"][0]["rerank_reasons"]


async def test_rag_retrieval_graph_falls_back_to_original_question_on_bad_rewrite(
    monkeypatch,
) -> None:
    seen_queries: list[str] = []

    async def fake_invoke_chat(*args, **kwargs):  # type: ignore[no-untyped-def]
        return _llm_result("not json")

    async def fake_probe_task_knowledge_chunks(**kwargs):  # type: ignore[no-untyped-def]
        seen_queries.append(str(kwargs["query_text"]))
        return []

    monkeypatch.setattr(
        "app.services.llm_runtime_service.LLMRuntimeService.invoke_chat",
        fake_invoke_chat,
    )
    monkeypatch.setattr(
        "app.services.qdrant_service.QdrantService.probe_task_knowledge_chunks",
        fake_probe_task_knowledge_chunks,
    )

    result = await run_rag_retrieval_graph(
        db=object(),
        actor_user_id="user-1",
        task_id="task-1",
        project_id=None,
        task_title="",
        task_status="draft",
        task_content="",
        question="Что во вложении?",
        retrieval_limit=2,
    )

    assert result["query_rewriter_ok"] is False
    assert result["query_rewriter_provider_kind"] == "openai"
    assert result["query_rewriter_model"] == "gpt-4o-mini"
    assert result["retrieval_queries"] == ["Что во вложении?"]
    assert seen_queries == ["Что во вложении?"]
