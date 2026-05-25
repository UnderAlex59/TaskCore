from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any, cast

from langgraph.graph import END, START, StateGraph

from app.agents.state import ChatState
from app.agents.system_prompts import VALIDATION_EVAL_QUESTION_JUDGE_SYSTEM_PROMPT
from app.services.graph_run_tracing import get_current_graph_run_id, run_traced_graph, traced_node
from app.services.llm_runtime_service import LLMRuntimeService

VALIDATION_EVAL_QUESTION_JUDGE_AGENT_KEY = "validation-eval-question-judge"
VALIDATION_EVAL_QUESTION_JUDGE_AGENT_NAME = "ValidationEvalQuestionJudgeAgent"
VALIDATION_EVAL_QUESTION_JUDGE_AGENT_DESCRIPTION = (
    "Оценивает качество уточняющих вопросов validation eval по relevance, "
    "specificity, actionability и novelty."
)
VALIDATION_EVAL_QUESTION_JUDGE_AGENT_ALIASES: tuple[str, ...] = ()


class ValidationEvalQuestionJudgeState(ChatState, total=False):
    db: Any
    actor_user_id: str | None
    project_id: str | None
    task_title: str
    task_content: str
    expected_questions: list[str]
    actual_questions: list[str]
    judge_system_prompt: str
    judge_user_prompt: str
    judge_payload: dict[str, object]
    judge_ok: bool
    judge_error_message: str | None
    judge_provider_kind: str | None
    judge_model: str | None
    provider_config_id: str | None
    judge_provider_config_id: str | None
    judge_graph_run_id: str | None


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


def _prepare_question_judge_prompt(
    state: ValidationEvalQuestionJudgeState,
) -> ValidationEvalQuestionJudgeState:
    return {
        "judge_system_prompt": VALIDATION_EVAL_QUESTION_JUDGE_SYSTEM_PROMPT,
        "judge_user_prompt": (
            "Название задачи:\n"
            f"{state.get('task_title', '')}\n\n"
            "Описание задачи:\n"
            f"{state.get('task_content', '')}\n\n"
            "Ожидаемые вопросы:\n"
            f"{json.dumps(list(state.get('expected_questions', [])), ensure_ascii=False)}\n\n"
            "Фактические вопросы:\n"
            f"{json.dumps(list(state.get('actual_questions', [])), ensure_ascii=False)}"
        ),
    }


async def _invoke_question_judge(
    state: ValidationEvalQuestionJudgeState,
) -> ValidationEvalQuestionJudgeState:
    db = state.get("db")
    if db is None:
        return {
            "judge_ok": False,
            "judge_error_message": "LLM runtime skipped: no database session.",
            "judge_provider_kind": None,
            "judge_model": None,
            "judge_provider_config_id": state.get("provider_config_id"),
            "judge_payload": {},
        }

    result = await LLMRuntimeService.invoke_chat(
        db,
        agent_key=VALIDATION_EVAL_QUESTION_JUDGE_AGENT_KEY,
        actor_user_id=state.get("actor_user_id"),
        task_id=None,
        project_id=state.get("project_id"),
        system_prompt=str(state.get("judge_system_prompt", "")),
        user_prompt=str(state.get("judge_user_prompt", "")),
        prompt_key=VALIDATION_EVAL_QUESTION_JUDGE_AGENT_KEY,
        provider_config_id=state.get("provider_config_id"),
    )
    return {
        "judge_ok": bool(result.ok),
        "judge_error_message": result.error_message,
        "judge_provider_kind": result.provider_kind,
        "judge_model": result.model,
        "judge_provider_config_id": result.provider_config_id,
        "judge_payload": (
            _extract_json_payload(result.text or "") if result.ok and result.text else {}
        )
        or {},
    }


def _score(value: object) -> float:
    try:
        score = float(cast(Any, value))
    except (TypeError, ValueError):
        return 0.0
    return min(1.0, max(0.0, score))


def _finalize_question_judge(
    state: ValidationEvalQuestionJudgeState,
) -> ValidationEvalQuestionJudgeState:
    payload = state.get("judge_payload") if state.get("judge_ok") else {}
    if not isinstance(payload, dict):
        payload = {}
    return {
        "judge_payload": {
            "relevance": _score(payload.get("relevance")),
            "specificity": _score(payload.get("specificity")),
            "actionability": _score(payload.get("actionability")),
            "novelty": _score(payload.get("novelty")),
            "rationale": str(
                payload.get("rationale")
                or state.get("judge_error_message")
                or "Judge did not return valid JSON."
            ),
            "provider_config_id": state.get("judge_provider_config_id"),
            "provider_kind": state.get("judge_provider_kind"),
            "model": state.get("judge_model"),
            "ok": bool(state.get("judge_ok")),
        },
        "judge_graph_run_id": get_current_graph_run_id(),
    }


@lru_cache
def get_validation_eval_question_judge_graph() -> Any:
    graph = StateGraph(ValidationEvalQuestionJudgeState)
    graph.add_node(
        "prepare_question_judge_prompt",
        cast(
            Any,
            traced_node("prepare_question_judge_prompt", _prepare_question_judge_prompt),
        ),
    )
    graph.add_node(
        "invoke_question_judge",
        cast(Any, traced_node("invoke_question_judge", _invoke_question_judge)),
    )
    graph.add_node(
        "finalize_question_judge",
        cast(Any, traced_node("finalize_question_judge", _finalize_question_judge)),
    )
    graph.add_edge(START, "prepare_question_judge_prompt")
    graph.add_edge("prepare_question_judge_prompt", "invoke_question_judge")
    graph.add_edge("invoke_question_judge", "finalize_question_judge")
    graph.add_edge("finalize_question_judge", END)
    return graph.compile()


async def run_validation_eval_question_judge_graph(
    *,
    db: Any,
    actor_user_id: str | None,
    project_id: str | None,
    task_title: str,
    task_content: str,
    expected_questions: list[str],
    actual_questions: list[str],
    provider_config_id: str | None = None,
) -> ValidationEvalQuestionJudgeState:
    state = await run_traced_graph(
        graph_key="validation_eval_question_judge_graph",
        graph=get_validation_eval_question_judge_graph(),
        source="validation_eval",
        force_trace=True,
        input_state={
            "db": db,
            "actor_user_id": actor_user_id,
            "project_id": project_id,
            "task_title": task_title,
            "task_content": task_content,
            "expected_questions": expected_questions,
            "actual_questions": actual_questions,
            "provider_config_id": provider_config_id,
        },
    )
    return {
        "judge_payload": dict(state.get("judge_payload", {})),
        "judge_ok": bool(state.get("judge_ok", False)),
        "judge_error_message": state.get("judge_error_message"),
        "judge_provider_kind": state.get("judge_provider_kind"),
        "judge_model": state.get("judge_model"),
        "judge_provider_config_id": state.get("judge_provider_config_id"),
        "judge_graph_run_id": state.get("judge_graph_run_id"),
    }
