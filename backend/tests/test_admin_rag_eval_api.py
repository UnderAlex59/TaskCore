from __future__ import annotations

import asyncio
from typing import Any

import pytest
from httpx import AsyncClient

from app.services.admin_rag_eval_service import AdminRagEvalService


async def register_and_login(
    client: AsyncClient,
    *,
    email: str,
    full_name: str,
) -> str:
    register_response = await client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "StrongPass1",
            "full_name": full_name,
        },
    )
    assert register_response.status_code == 201

    login_response = await client.post(
        "/auth/login",
        json={"email": email, "password": "StrongPass1"},
    )
    assert login_response.status_code == 200
    return str(login_response.json()["access_token"])


async def create_project(client: AsyncClient, token: str, *, name: str = "RAG Eval") -> str:
    response = await client.post(
        "/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name, "description": "Eval project"},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def import_payload(project_id: str, *, title: str = "Авторизация") -> dict[str, Any]:
    return {
        "format": "json",
        "payload": {
            "dataset_name": "RAG eval set",
            "project_id": project_id,
            "tasks": [
                {
                    "external_id": "task-auth-1",
                    "title": title,
                    "content": "Описание задачи с корректной русской кодировкой.",
                    "tags": ["auth", "security"],
                    "attachments": [
                        {
                            "filename": "requirements.txt",
                            "content_type": "text/plain",
                            "content": "Текстовое вложение про авторизацию.",
                        }
                    ],
                }
            ],
            "cases": [
                {
                    "external_id": "case-1",
                    "task_external_id": "task-auth-1",
                    "question": "Какие требования к авторизации?",
                    "expected_answer": "Нужно описать требования к авторизации.",
                    "expected_relevant": [
                        {
                            "task_external_id": "task-auth-1",
                            "source_type": "task_content",
                            "text_contains": "русской кодировкой",
                        }
                    ],
                }
            ],
        },
    }


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_admin_can_import_rag_eval_dataset_idempotently(client: AsyncClient) -> None:
    token = await register_and_login(
        client,
        email="rag-eval-import@example.com",
        full_name="RAG Eval Admin",
    )
    project_id = await create_project(client, token)

    first_response = await client.post(
        "/admin/rag-eval/datasets/import",
        headers={"Authorization": f"Bearer {token}"},
        json=import_payload(project_id),
    )
    assert first_response.status_code == 201
    first_payload = first_response.json()
    assert first_payload["created_tasks"] == 1
    assert first_payload["updated_tasks"] == 0
    assert first_payload["dataset"]["cases_total"] == 1
    assert (
        "русской" in first_payload["dataset"]["cases"][0]["expected_relevant"][0]["text_contains"]
    )

    second_response = await client.post(
        "/admin/rag-eval/datasets/import",
        headers={"Authorization": f"Bearer {token}"},
        json=import_payload(project_id, title="Авторизация пользователей"),
    )
    assert second_response.status_code == 201
    second_payload = second_response.json()
    assert second_payload["created_tasks"] == 0
    assert second_payload["updated_tasks"] == 1
    assert second_payload["dataset"]["tasks_total"] == 1
    assert second_payload["dataset"]["tasks"][0]["title"] == "Авторизация пользователей"


def test_case_metrics_calculates_recall_and_mrr() -> None:
    metrics, matched = AdminRagEvalService._case_metrics(
        expected_relevant=[
            {
                "task_external_id": "task-1",
                "source_type": "task_content",
                "text_contains": "SLA",
            }
        ],
        retrieved_chunks=[
            {
                "chunk_id": "chunk-0",
                "task_id": "task-db-id",
                "source_type": "attachment_text",
                "content": "Other context",
            },
            {
                "chunk_id": "chunk-1",
                "task_id": "task-db-id",
                "source_type": "task_content",
                "content": "SLA входа 15 минут",
            },
        ],
        task_id_by_external_id={"task-1": "task-db-id"},
    )

    assert metrics["recall_at_1"] is False
    assert metrics["recall_at_3"] is True
    assert metrics["mrr"] == 0.5
    assert matched[0]["rank"] == 2


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_admin_can_run_rag_eval_with_stubbed_agents(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = await register_and_login(
        client,
        email="rag-eval-run@example.com",
        full_name="RAG Eval Runner",
    )
    project_id = await create_project(client, token, name="RAG Eval Run")
    import_response = await client.post(
        "/admin/rag-eval/datasets/import",
        headers={"Authorization": f"Bearer {token}"},
        json=import_payload(project_id),
    )
    assert import_response.status_code == 201
    dataset_id = import_response.json()["dataset"]["id"]

    async def fake_index(*args, **kwargs):  # type: ignore[no-untyped-def]
        return {
            "chunk_ids": ["chunk-1"],
            "indexed": True,
            "attachment_payload_ms": 1,
            "chunking_ms": 2,
            "embedding_and_qdrant_write_ms": 3,
            "qdrant_cleanup_ms": None,
            "total_index_ms": 6,
            "chunks_total": 1,
        }

    async def fake_retrieval(**kwargs):  # type: ignore[no-untyped-def]
        return {
            "reranked_chunks": [
                {
                    "chunk_id": "chunk-1",
                    "task_id": kwargs["task_id"],
                    "source_type": "task_content",
                    "chunk_index": 0,
                    "score": 0.91,
                    "threshold": 0.3,
                    "content": "Описание задачи с корректной русской кодировкой.",
                }
            ],
            "rag_chunk_ids": ["chunk-1"],
            "rag_context_scope": "attachments",
        }

    async def fake_qa(**kwargs):  # type: ignore[no-untyped-def]
        return {
            "response": "Требования к авторизации описаны в задаче.",
            "source_ref": {"answer_confidence": "high"},
        }

    async def fake_judge(**kwargs):  # type: ignore[no-untyped-def]
        return {
            "judge_payload": {
                "groundedness": "grounded",
                "correctness": "correct",
                "unsupported_claims": [],
                "rationale": "Ответ подтверждён.",
            }
        }

    monkeypatch.setattr(
        "app.services.admin_rag_eval_service.RagService.index_task_context_with_metrics",
        fake_index,
    )
    monkeypatch.setattr(
        "app.services.admin_rag_eval_service.run_rag_retrieval_graph",
        fake_retrieval,
    )
    monkeypatch.setattr(
        "app.services.admin_rag_eval_service.run_qa_agent_graph",
        fake_qa,
    )
    monkeypatch.setattr(
        "app.services.admin_rag_eval_service.run_rag_eval_judge_graph",
        fake_judge,
    )

    run_response = await client.post(
        f"/admin/rag-eval/datasets/{dataset_id}/runs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "indexing_mode": "all",
            "retrieval_limit": 5,
            "use_query_rewriter": False,
            "use_hybrid_rerank": True,
            "include_cross_task": True,
            "include_current_task_content": False,
            "run_answer_agent": True,
            "run_llm_judge": True,
            "min_score_override": None,
        },
    )
    assert run_response.status_code == 201
    run_id = run_response.json()["id"]

    detail = None
    for _ in range(10):
        detail_response = await client.get(
            f"/admin/rag-eval/runs/{run_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert detail_response.status_code == 200
        detail = detail_response.json()
        if detail["status"] == "success":
            break
        await asyncio.sleep(0.1)

    assert detail is not None
    assert detail["status"] == "success"
    assert detail["summary_metrics"]["recall_at_5"] == 1
    assert detail["summary_metrics"]["groundedness"]["grounded"] == 1
    assert detail["case_results"][0]["metrics"]["correctness"] == "correct"

    export_response = await client.get(
        f"/admin/rag-eval/runs/{run_id}/export?format=csv",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert export_response.status_code == 200
    assert "case_external_id" in export_response.text
