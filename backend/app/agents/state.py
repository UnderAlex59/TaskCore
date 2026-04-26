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


class VisionAltTextState(TypedDict, total=False):
    task_id: str | None
    project_id: str | None
    alt_text: str | None


class ProviderTestState(TypedDict, total=False):
    provider_id: str
    actor_user_id: str | None
    ok: bool
    provider_kind: str
    model: str
    latency_ms: int | None
    message: str


class VisionTestState(TypedDict, total=False):
    actor_user_id: str | None
    content_type: str
    ok: bool
    provider_config_id: str | None
    provider_kind: str
    provider_name: str | None
    model: str
    latency_ms: int | None
    prompt: str
    result_text: str | None
    message: str
