from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.requires_db


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


@pytest.mark.asyncio
async def test_admin_can_fetch_qdrant_overview(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    access_token = await register_and_login(
        client,
        email="admin-qdrant-overview@example.com",
        full_name="Admin Qdrant",
    )

    async def fake_overview():  # type: ignore[no-untyped-def]
        return {
            "connected": True,
            "connection_error": None,
            "qdrant_url": "http://localhost:6333",
            "embedding_provider": "openai",
            "embedding_model": "text-embedding-3-small",
            "expected_vector_size": 1536,
            "generated_at": "2026-04-27T12:00:00Z",
            "collections": [
                {
                    "collection_name": "task_knowledge",
                    "exists": True,
                    "status": "green",
                    "points_count": 3,
                    "vectors_count": 3,
                    "indexed_vectors_count": 3,
                    "segments_count": 1,
                    "vector_size": 1536,
                    "distance": "Cosine",
                    "metadata": {
                        "embedding_provider": "openai",
                        "embedding_model": "text-embedding-3-small",
                    },
                    "sample_payload_keys": ["task_id", "task_title"],
                    "provider_matches": True,
                    "model_matches": True,
                    "vector_size_matches": True,
                    "metadata_matches_active_embeddings": True,
                    "warnings": [],
                    "error": None,
                }
            ],
        }

    monkeypatch.setattr(
        "app.services.admin_qdrant_service.AdminQdrantService.get_overview",
        fake_overview,
    )

    response = await client.get(
        "/admin/qdrant/overview",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["connected"] is True
    assert payload["collections"][0]["collection_name"] == "task_knowledge"


@pytest.mark.asyncio
async def test_admin_can_probe_duplicate_proposal_scenario(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    access_token = await register_and_login(
        client,
        email="admin-qdrant-scenario@example.com",
        full_name="Admin Scenario",
    )

    async def fake_probe(payload, db):  # type: ignore[no-untyped-def]
        return {
            "scenario": "duplicate_proposal",
            "project_id": payload.project_id,
            "task_id": payload.task_id,
            "query_text": payload.proposal_text,
            "heuristic_status": "warning",
            "heuristics": [
                {
                    "code": "near_threshold_duplicate",
                    "status": "warning",
                    "message": "Найдено очень похожее предложение.",
                }
            ],
            "results": [
                {
                    "id": "proposal-1",
                    "task_id": "task-1",
                    "task_title": "Синхронизация статусов",
                    "task_status": "in_progress",
                    "score": 0.9,
                    "snippet": "Добавить двустороннюю синхронизацию статусов.",
                    "metadata": {"status": "new"},
                    "match_band": "near_threshold",
                }
            ],
            "raw_threshold": 0.92,
        }

    monkeypatch.setattr(
        "app.services.admin_qdrant_service.AdminQdrantService.probe_duplicate_proposal",
        fake_probe,
    )

    response = await client.post(
        "/admin/qdrant/scenarios/duplicate-proposal",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "project_id": "project-1",
            "proposal_text": "Добавить двустороннюю синхронизацию статусов.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["heuristic_status"] == "warning"
    assert payload["results"][0]["match_band"] == "near_threshold"
    assert payload["raw_threshold"] == 0.92
