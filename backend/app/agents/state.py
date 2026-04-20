from __future__ import annotations

from typing import Any, TypedDict


class ValidationState(TypedDict, total=False):
    task_id: str
    issues: list[dict[str, str]]
    questions: list[str]
    verdict: str


class ChatState(TypedDict, total=False):
    task_id: str
    message_id: str
    source_message_id: str
    ai_response_required: bool
    agent_name: str
    message_type: str
    response: str
    source_ref: dict[str, Any]
    proposal_text: str


class RagIndexState(TypedDict, total=False):
    task_id: str
    indexed: bool
    chunk_ids: list[str]
    chunks: list[dict[str, Any]]


class ProviderTestState(TypedDict, total=False):
    provider_id: str
    actor_user_id: str | None
    ok: bool
    provider_kind: str
    model: str
    latency_ms: int | None
    message: str
