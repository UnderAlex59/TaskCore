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
    agent_name: str
    message_type: str
    response: str
    source_ref: dict[str, Any]
    proposal_text: str


class RagIndexState(TypedDict, total=False):
    task_id: str
    indexed: bool
    chunk_ids: list[str]
