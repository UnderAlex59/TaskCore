from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.state import ChatState
from app.agents.system_prompts import QURE_EVAL_WEAK_WORD_JUDGE_SYSTEM_PROMPT
from app.services.graph_run_tracing import get_current_graph_run_id, run_traced_graph, traced_node
from app.services.llm_runtime_service import LLMRuntimeService

QURE_EVAL_WEAK_WORD_JUDGE_AGENT_KEY = "qure-eval-weak-word-judge"
QURE_EVAL_WEAK_WORD_JUDGE_AGENT_NAME = "QuREEvalWeakWordJudgeAgent"
QURE_EVAL_WEAK_WORD_JUDGE_AGENT_DESCRIPTION = (
    "Принимает итоговое решение о прохождении QuRE Eval кейса по ответу валидатора."
)
QURE_EVAL_WEAK_WORD_JUDGE_AGENT_ALIASES: tuple[str, ...] = ()


class QureEvalWeakWordJudgeState(ChatState, total=False):
    db: Any
    actor_user_id: str | None
    project_id: str | None
    requirement: str
    weak_word: str
    qure_defect: str
    expected_verdict: str
    actual_verdict: str
    actual_issues: list[dict[str, Any]]
    judge_system_prompt: str
    judge_user_prompt: str
    judge_payload: dict[str, object]
    judge_ok: bool
    judge_error_message: str | None
    judge_provider_kind: str | None
    judge_model: str | None
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


def _prepare_judge_prompt(state: QureEvalWeakWordJudgeState) -> QureEvalWeakWordJudgeState:
    return {
        "judge_system_prompt": QURE_EVAL_WEAK_WORD_JUDGE_SYSTEM_PROMPT,
        "judge_user_prompt": (
            "Requirement:\n"
            f"{state.get('requirement', '')}\n\n"
            "Weak word:\n"
            f"{state.get('weak_word', '')}\n\n"
            "QuRE label:\n"
            f"{state.get('qure_defect', '')}\n\n"
            "Expected validator verdict:\n"
            f"{state.get('expected_verdict', '')}\n\n"
            "Actual validator verdict:\n"
            f"{state.get('actual_verdict', '')}\n\n"
            "Actual validator issues:\n"
            f"{json.dumps(list(state.get('actual_issues', [])), ensure_ascii=False)}"
        ),
    }


async def _invoke_judge(state: QureEvalWeakWordJudgeState) -> QureEvalWeakWordJudgeState:
    db = state.get("db")
    if db is None:
        return {
            "judge_ok": False,
            "judge_error_message": "LLM runtime skipped: no database session.",
            "judge_provider_kind": None,
            "judge_model": None,
            "judge_payload": {},
        }

    result = await LLMRuntimeService.invoke_chat(
        db,
        agent_key=QURE_EVAL_WEAK_WORD_JUDGE_AGENT_KEY,
        actor_user_id=state.get("actor_user_id"),
        task_id=None,
        project_id=state.get("project_id"),
        system_prompt=str(state.get("judge_system_prompt", "")),
        user_prompt=str(state.get("judge_user_prompt", "")),
        prompt_key=QURE_EVAL_WEAK_WORD_JUDGE_AGENT_KEY,
    )
    return {
        "judge_ok": bool(result.ok),
        "judge_error_message": result.error_message,
        "judge_provider_kind": result.provider_kind,
        "judge_model": result.model,
        "judge_payload": _extract_json_payload(result.text or "")
        if result.ok and result.text
        else {},
    }


def _score(value: object) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return min(1.0, max(0.0, score))


def _bool_or_none(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"false", "no", "0"}:
            return False
    return None


def _indices(value: object, issues_count: int) -> list[int]:
    if not isinstance(value, list):
        return []
    indices: list[int] = []
    for item in value:
        if not isinstance(item, int):
            continue
        if 0 <= item < issues_count and item not in indices:
            indices.append(item)
    return indices


def _finalize_judge(state: QureEvalWeakWordJudgeState) -> QureEvalWeakWordJudgeState:
    payload = state.get("judge_payload") if state.get("judge_ok") else {}
    if not isinstance(payload, dict):
        payload = {}
    actual_issues = list(state.get("actual_issues", []))
    passed = _bool_or_none(payload.get("passed"))
    if passed is None:
        passed = _bool_or_none(payload.get("match"))
    verdict_match = _bool_or_none(payload.get("verdict_match"))
    weak_word_match = _bool_or_none(payload.get("weak_word_match"))
    payload_ok = bool(state.get("judge_ok")) and passed is not None
    return {
        "judge_payload": {
            "passed": bool(passed) if passed is not None else False,
            "match": bool(passed) if passed is not None else False,
            "score": _score(payload.get("score")),
            "verdict_match": bool(verdict_match) if verdict_match is not None else False,
            "weak_word_match": bool(weak_word_match) if weak_word_match is not None else False,
            "matched_issue_indices": _indices(
                payload.get("matched_issue_indices"),
                len(actual_issues),
            ),
            "rationale": str(
                payload.get("rationale")
                or state.get("judge_error_message")
                or "Judge did not return a valid QuRE decision."
            ),
            "provider_kind": state.get("judge_provider_kind"),
            "model": state.get("judge_model"),
            "ok": payload_ok,
        },
        "judge_graph_run_id": get_current_graph_run_id(),
    }


@lru_cache
def get_qure_eval_weak_word_judge_graph():
    graph = StateGraph(QureEvalWeakWordJudgeState)
    graph.add_node(
        "prepare_judge_prompt",
        traced_node("prepare_judge_prompt", _prepare_judge_prompt),
    )
    graph.add_node("invoke_judge", traced_node("invoke_judge", _invoke_judge))
    graph.add_node("finalize_judge", traced_node("finalize_judge", _finalize_judge))
    graph.add_edge(START, "prepare_judge_prompt")
    graph.add_edge("prepare_judge_prompt", "invoke_judge")
    graph.add_edge("invoke_judge", "finalize_judge")
    graph.add_edge("finalize_judge", END)
    return graph.compile()


async def run_qure_eval_weak_word_judge_graph(
    *,
    db: Any,
    actor_user_id: str | None,
    project_id: str | None,
    requirement: str,
    weak_word: str,
    qure_defect: str,
    expected_verdict: str,
    actual_verdict: str,
    actual_issues: list[dict[str, Any]],
) -> QureEvalWeakWordJudgeState:
    state = await run_traced_graph(
        graph_key="qure_eval_weak_word_judge_graph",
        graph=get_qure_eval_weak_word_judge_graph(),
        source="qure_eval",
        force_trace=True,
        input_state={
            "db": db,
            "actor_user_id": actor_user_id,
            "project_id": project_id,
            "requirement": requirement,
            "weak_word": weak_word,
            "qure_defect": qure_defect,
            "expected_verdict": expected_verdict,
            "actual_verdict": actual_verdict,
            "actual_issues": actual_issues,
        },
    )
    judge_payload = dict(state.get("judge_payload", {}))
    return {
        "judge_payload": judge_payload,
        "judge_ok": bool(judge_payload.get("ok")),
        "judge_error_message": state.get("judge_error_message"),
        "judge_provider_kind": state.get("judge_provider_kind"),
        "judge_model": state.get("judge_model"),
        "judge_graph_run_id": state.get("judge_graph_run_id"),
    }
