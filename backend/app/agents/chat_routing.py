from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from app.agents.system_prompts import CHAT_ROUTING_SYSTEM_PROMPT

CHAT_ROUTING_AGENT_KEY = "chat-routing"
CHAT_ROUTING_AGENT_NAME = "ChatRoutingAgent"
CHAT_ROUTING_AGENT_DESCRIPTION = (
    "Выбирает, нужен ли ответ ИИ в чате задачи и какой agent subgraph должен его обработать."
)
CHAT_ROUTING_AGENT_ALIASES: tuple[str, ...] = ()

_MESSAGE_TYPES = {"general", "question", "change_proposal"}
_NULL_TARGET_VALUES = {"", "none", "null", "no", "нет", "skip", "false"}


@dataclass(frozen=True, slots=True)
class ChatRoutingOutcome:
    ai_response_required: bool
    target_agent_key: str | None
    message_type: str
    reason: str
    status: str
    provider_kind: str | None = None
    model: str | None = None
    parse_error: str | None = None
    runtime_error: str | None = None

    def source_ref(self, *, mode: str = "auto") -> dict[str, object]:
        payload: dict[str, object] = {
            "mode": mode,
            "status": self.status,
            "ai_response_required": self.ai_response_required,
            "target_agent_key": self.target_agent_key,
            "message_type": self.message_type,
            "reason": self.reason,
            "provider_kind": self.provider_kind,
            "model": self.model,
        }
        if self.parse_error:
            payload["parse_error"] = self.parse_error
        if self.runtime_error:
            payload["runtime_error"] = self.runtime_error
        return payload


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


def _normalize_bool(candidate: object) -> bool | None:
    if isinstance(candidate, bool):
        return candidate
    normalized = str(candidate).strip().casefold()
    if normalized in {"true", "yes", "1"}:
        return True
    if normalized in {"false", "no", "0"}:
        return False
    return None


def _default_message_type_for_target(target_agent_key: str | None) -> str:
    if target_agent_key == "qa":
        return "question"
    if target_agent_key == "change-tracker":
        return "change_proposal"
    return "general"


def _normalize_message_type(candidate: object, *, fallback: str) -> str:
    normalized = str(candidate or "").strip().casefold()
    if normalized in _MESSAGE_TYPES:
        return normalized
    return fallback


def _normalize_target_agent_key(
    candidate: object,
    *,
    available_agent_keys: set[str],
) -> str | None:
    normalized = str(candidate or "").strip().casefold()
    if normalized in _NULL_TARGET_VALUES:
        return None
    if normalized in available_agent_keys:
        return normalized
    return "__invalid__"


def normalize_chat_routing_decision(
    payload: dict[str, object],
    *,
    available_agent_keys: set[str],
) -> tuple[ChatRoutingOutcome | None, str | None]:
    ai_response_required = _normalize_bool(payload.get("ai_response_required"))
    if ai_response_required is None:
        return None, "missing_or_invalid_ai_response_required"

    reason = str(payload.get("reason") or "").strip()
    target_agent_key = _normalize_target_agent_key(
        payload.get("target_agent_key"),
        available_agent_keys=available_agent_keys,
    )

    if not ai_response_required:
        return (
            ChatRoutingOutcome(
                ai_response_required=False,
                target_agent_key=None,
                message_type=_normalize_message_type(
                    payload.get("message_type"),
                    fallback="general",
                ),
                reason=reason or "no_agent_response_required",
                status="skipped",
            ),
            None,
        )

    if target_agent_key is None:
        return None, "missing_target_agent_key"
    if target_agent_key == "__invalid__":
        return None, "invalid_target_agent_key"

    message_type = _normalize_message_type(
        payload.get("message_type"),
        fallback=_default_message_type_for_target(target_agent_key),
    )
    return (
        ChatRoutingOutcome(
            ai_response_required=True,
            target_agent_key=target_agent_key,
            message_type=message_type,
            reason=reason or f"auto_agent:{target_agent_key}",
            status="routed",
        ),
        None,
    )


def build_chat_routing_user_prompt(
    *,
    task_title: str,
    task_status: str,
    task_content: str,
    message_content: str,
    available_agents: list[dict[str, object]],
) -> str:
    return (
        "Доступные agent subgraphs для auto-routing:\n"
        f"{json.dumps(available_agents, ensure_ascii=False)}\n\n"
        "Название задачи:\n"
        f"{task_title.strip()}\n\n"
        "Статус задачи:\n"
        f"{task_status.strip()}\n\n"
        "Описание задачи:\n"
        f"{task_content.strip()}\n\n"
        "Сообщение пользователя:\n"
        f"{message_content.strip()}\n\n"
        "Верни строго JSON по схеме:\n"
        '{"ai_response_required": boolean, "target_agent_key": string|null, '
        '"message_type": "general"|"question"|"change_proposal", "reason": string}'
    )


async def analyze_chat_routing(
    *,
    db: Any,
    actor_user_id: str | None,
    task_id: str | None,
    project_id: str | None,
    task_title: str,
    task_status: str,
    task_content: str,
    message_content: str,
    available_agents: list[dict[str, object]],
) -> ChatRoutingOutcome:
    if db is None:
        return ChatRoutingOutcome(
            ai_response_required=False,
            target_agent_key=None,
            message_type="general",
            reason="LLM routing requires database-backed runtime settings.",
            status="error",
            runtime_error="db_session_missing",
        )

    from app.services.llm_runtime_service import LLMRuntimeService

    try:
        result = await LLMRuntimeService.invoke_chat(
            db,
            agent_key=CHAT_ROUTING_AGENT_KEY,
            actor_user_id=actor_user_id,
            task_id=task_id,
            project_id=project_id,
            system_prompt=CHAT_ROUTING_SYSTEM_PROMPT,
            user_prompt=build_chat_routing_user_prompt(
                task_title=task_title,
                task_status=task_status,
                task_content=task_content,
                message_content=message_content,
                available_agents=available_agents,
            ),
            prompt_key=CHAT_ROUTING_AGENT_KEY,
        )
    except Exception as exc:  # noqa: BLE001
        return ChatRoutingOutcome(
            ai_response_required=False,
            target_agent_key=None,
            message_type="general",
            reason="LLM router raised an exception.",
            status="error",
            runtime_error=str(exc),
        )
    if not result.ok:
        return ChatRoutingOutcome(
            ai_response_required=False,
            target_agent_key=None,
            message_type="general",
            reason="LLM router failed.",
            status="error",
            provider_kind=result.provider_kind,
            model=result.model,
            runtime_error=result.error_message or "llm_router_failed",
        )

    payload = _extract_json_payload(result.text or "")
    if payload is None:
        return ChatRoutingOutcome(
            ai_response_required=False,
            target_agent_key=None,
            message_type="general",
            reason="LLM router returned malformed JSON.",
            status="error",
            provider_kind=result.provider_kind,
            model=result.model,
            parse_error="malformed_json",
        )

    available_agent_keys = {str(item["key"]).casefold() for item in available_agents}
    outcome, validation_error = normalize_chat_routing_decision(
        payload,
        available_agent_keys=available_agent_keys,
    )
    if outcome is None:
        return ChatRoutingOutcome(
            ai_response_required=False,
            target_agent_key=None,
            message_type="general",
            reason="LLM router returned an invalid routing decision.",
            status="error",
            provider_kind=result.provider_kind,
            model=result.model,
            parse_error=validation_error or "invalid_routing_decision",
        )

    return ChatRoutingOutcome(
        ai_response_required=outcome.ai_response_required,
        target_agent_key=outcome.target_agent_key,
        message_type=outcome.message_type,
        reason=outcome.reason,
        status=outcome.status,
        provider_kind=result.provider_kind,
        model=result.model,
    )
