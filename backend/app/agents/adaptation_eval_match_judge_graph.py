from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.state import ChatState
from app.agents.system_prompts import ADAPTATION_EVAL_MATCH_JUDGE_SYSTEM_PROMPT
from app.services.graph_run_tracing import get_current_graph_run_id, run_traced_graph, traced_node
from app.services.llm_runtime_service import LLMRuntimeService

ADAPTATION_EVAL_MATCH_JUDGE_AGENT_KEY = "adaptation-eval-match-judge"
ADAPTATION_EVAL_MATCH_JUDGE_AGENT_NAME = "AdaptationEvalMatchJudgeAgent"
ADAPTATION_EVAL_MATCH_JUDGE_AGENT_DESCRIPTION = (
    "Сопоставляет expected и actual элементы Adaptation Eval по смысловой эквивалентности."
)
ADAPTATION_EVAL_MATCH_JUDGE_AGENT_ALIASES: tuple[str, ...] = ()


class AdaptationEvalMatchJudgeState(ChatState, total=False):
    db: Any
    actor_user_id: str | None
    project_id: str | None
    case_external_id: str
    scenario_type: str
    group_key: str
    task_title: str
    task_content: str
    expected_items: list[dict[str, Any]]
    actual_items: list[dict[str, Any]]
    judge_system_prompt: str
    judge_user_prompt: str
    judge_payload: dict[str, object]
    judge_ok: bool
    judge_error_message: str | None
    judge_provider_kind: str | None
    judge_model: str | None
    judge_graph_run_id: str | None
    invalid_json_count: int
    retry_count: int
    raw_response: str | None


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


def _prepare_match_judge_prompt(
    state: AdaptationEvalMatchJudgeState,
) -> AdaptationEvalMatchJudgeState:
    context = {
        "case_external_id": state.get("case_external_id"),
        "scenario_type": state.get("scenario_type"),
        "group_key": state.get("group_key"),
        "task_title": state.get("task_title"),
        "task_content": state.get("task_content"),
    }
    return {
        "judge_system_prompt": ADAPTATION_EVAL_MATCH_JUDGE_SYSTEM_PROMPT,
        "judge_user_prompt": (
            "Контекст кейса:\n"
            f"{json.dumps(context, ensure_ascii=False)}\n\n"
            "expected_items:\n"
            f"{json.dumps(list(state.get('expected_items', [])), ensure_ascii=False)}\n\n"
            "actual_items:\n"
            f"{json.dumps(list(state.get('actual_items', [])), ensure_ascii=False)}\n\n"
            "Используй значения index из элементов как expected_index и actual_index."
        ),
    }


async def _invoke_once(
    state: AdaptationEvalMatchJudgeState,
    *,
    user_prompt: str,
    temperature_override: float | None,
) -> tuple[dict[str, object] | None, dict[str, Any]]:
    db = state.get("db")
    if db is None:
        return None, {
            "ok": False,
            "error_message": "LLM runtime skipped: no database session.",
            "provider_kind": None,
            "model": None,
            "raw_response": None,
        }

    result = await LLMRuntimeService.invoke_chat(
        db,
        agent_key=ADAPTATION_EVAL_MATCH_JUDGE_AGENT_KEY,
        actor_user_id=state.get("actor_user_id"),
        task_id=None,
        project_id=state.get("project_id"),
        system_prompt=str(state.get("judge_system_prompt", "")),
        user_prompt=user_prompt,
        prompt_key=ADAPTATION_EVAL_MATCH_JUDGE_AGENT_KEY,
        temperature_override=temperature_override,
    )
    payload = _extract_json_payload(result.text or "") if result.ok and result.text else None
    return payload, {
        "ok": bool(result.ok),
        "error_message": result.error_message,
        "provider_kind": result.provider_kind,
        "model": result.model,
        "raw_response": result.text,
    }


async def _invoke_match_judge(
    state: AdaptationEvalMatchJudgeState,
) -> AdaptationEvalMatchJudgeState:
    prompt = str(state.get("judge_user_prompt", ""))
    payload, metadata = await _invoke_once(
        state,
        user_prompt=prompt,
        temperature_override=None,
    )
    invalid_json_count = 0
    retry_count = 0
    if metadata["ok"] and payload is None:
        invalid_json_count = 1
        retry_count = 1
        repair_prompt = (
            f"{prompt}\n\n"
            "Предыдущий ответ не был валидным JSON. Верни только исправленный JSON "
            "строго по схеме без markdown и пояснений.\n\n"
            "Предыдущий ответ:\n"
            f"{metadata.get('raw_response') or ''}"
        )
        payload, retry_metadata = await _invoke_once(
            state,
            user_prompt=repair_prompt,
            temperature_override=0.0,
        )
        metadata = retry_metadata
        if metadata["ok"] and payload is None:
            invalid_json_count += 1

    return {
        "judge_ok": bool(metadata["ok"] and payload is not None),
        "judge_error_message": metadata.get("error_message"),
        "judge_provider_kind": metadata.get("provider_kind"),
        "judge_model": metadata.get("model"),
        "judge_payload": payload or {},
        "invalid_json_count": invalid_json_count,
        "retry_count": retry_count,
        "raw_response": metadata.get("raw_response"),
    }


def _as_index(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_score(value: object) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return min(1.0, max(0.0, score))


def _normalize_payload(payload: dict[str, object]) -> dict[str, object]:
    raw_matches = payload.get("matches")
    matches: list[dict[str, object]] = []
    if isinstance(raw_matches, list):
        for item in raw_matches:
            if not isinstance(item, dict):
                continue
            expected_index = _as_index(item.get("expected_index"))
            actual_index = _as_index(item.get("actual_index"))
            if expected_index is None or actual_index is None:
                continue
            matches.append(
                {
                    "expected_index": expected_index,
                    "actual_index": actual_index,
                    "match": bool(item.get("match")),
                    "confidence": _as_score(item.get("confidence")),
                    "reason": str(item.get("reason") or ""),
                }
            )

    return {
        "matches": matches,
        "unmatched_expected_indices": _normalize_indices(
            payload.get("unmatched_expected_indices")
        ),
        "unmatched_actual_indices": _normalize_indices(
            payload.get("unmatched_actual_indices")
        ),
        "ok": bool(payload.get("ok", True)),
    }


def _normalize_indices(candidate: object) -> list[int]:
    if not isinstance(candidate, list):
        return []
    return [
        index
        for index in (_as_index(value) for value in candidate)
        if index is not None
    ]


def _finalize_match_judge(
    state: AdaptationEvalMatchJudgeState,
) -> AdaptationEvalMatchJudgeState:
    payload = state.get("judge_payload") if state.get("judge_ok") else {}
    if not isinstance(payload, dict):
        payload = {}
    normalized_payload = _normalize_payload(payload)
    normalized_payload.update(
        {
            "provider_kind": state.get("judge_provider_kind"),
            "model": state.get("judge_model"),
            "ok": bool(state.get("judge_ok")) and bool(normalized_payload.get("ok")),
            "error_message": state.get("judge_error_message"),
            "invalid_json_count": int(state.get("invalid_json_count") or 0),
            "retry_count": int(state.get("retry_count") or 0),
        }
    )
    return {
        "judge_payload": normalized_payload,
        "judge_graph_run_id": get_current_graph_run_id(),
    }


@lru_cache
def get_adaptation_eval_match_judge_graph():
    graph = StateGraph(AdaptationEvalMatchJudgeState)
    graph.add_node(
        "prepare_match_judge_prompt",
        traced_node("prepare_match_judge_prompt", _prepare_match_judge_prompt),
    )
    graph.add_node(
        "invoke_match_judge",
        traced_node("invoke_match_judge", _invoke_match_judge),
    )
    graph.add_node(
        "finalize_match_judge",
        traced_node("finalize_match_judge", _finalize_match_judge),
    )
    graph.add_edge(START, "prepare_match_judge_prompt")
    graph.add_edge("prepare_match_judge_prompt", "invoke_match_judge")
    graph.add_edge("invoke_match_judge", "finalize_match_judge")
    graph.add_edge("finalize_match_judge", END)
    return graph.compile()


async def run_adaptation_eval_match_judge_graph(
    *,
    db: Any,
    actor_user_id: str | None,
    project_id: str | None,
    case_external_id: str,
    scenario_type: str,
    group_key: str,
    task_title: str,
    task_content: str,
    expected_items: list[dict[str, Any]],
    actual_items: list[dict[str, Any]],
) -> AdaptationEvalMatchJudgeState:
    state = await run_traced_graph(
        graph_key="adaptation_eval_match_judge_graph",
        graph=get_adaptation_eval_match_judge_graph(),
        source="adaptation_eval",
        force_trace=isinstance(db, AsyncSession),
        input_state={
            "db": db,
            "actor_user_id": actor_user_id,
            "project_id": project_id,
            "case_external_id": case_external_id,
            "scenario_type": scenario_type,
            "group_key": group_key,
            "task_title": task_title,
            "task_content": task_content,
            "expected_items": expected_items,
            "actual_items": actual_items,
        },
    )
    return {
        "judge_payload": dict(state.get("judge_payload", {})),
        "judge_ok": bool(dict(state.get("judge_payload", {})).get("ok")),
        "judge_error_message": state.get("judge_error_message"),
        "judge_provider_kind": state.get("judge_provider_kind"),
        "judge_model": state.get("judge_model"),
        "judge_graph_run_id": state.get("judge_graph_run_id"),
    }
