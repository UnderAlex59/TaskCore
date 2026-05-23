from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.state import ChatState
from app.agents.system_prompts import RAG_EVAL_JUDGE_SYSTEM_PROMPT
from app.services.graph_run_tracing import run_traced_graph, traced_node
from app.services.llm_runtime_service import LLMRuntimeService

RAG_EVAL_JUDGE_AGENT_KEY = "rag-eval-judge"
RAG_EVAL_JUDGE_AGENT_NAME = "RAGEvalJudgeAgent"
RAG_EVAL_JUDGE_AGENT_DESCRIPTION = (
    "Оценивает groundedness и correctness ответов RAG-агента на фиксированном eval-наборе."
)
RAG_EVAL_JUDGE_AGENT_ALIASES: tuple[str, ...] = ()


class RagEvalJudgeState(ChatState, total=False):
    db: Any
    actor_user_id: str | None
    task_id: str | None
    project_id: str | None
    question: str
    expected_answer: str | None
    answer_text: str
    retrieved_chunks: list[dict[str, object]]
    judge_system_prompt: str
    judge_user_prompt: str
    judge_payload: dict[str, object] | None
    judge_ok: bool
    judge_error_message: str | None
    judge_provider_kind: str | None
    judge_model: str | None
    judge_provider_config_id: str | None


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


def _prepare_judge_prompt(state: RagEvalJudgeState) -> RagEvalJudgeState:
    chunks = []
    for index, chunk in enumerate(list(state.get("retrieved_chunks", []))[:8], start=1):
        chunks.append(
            f"[{index}] chunk_id={chunk.get('chunk_id') or chunk.get('id')}; "
            f"task_id={chunk.get('task_id')}; source_type={chunk.get('source_type')}\n"
            f"{str(chunk.get('content') or '')[:2000]}"
        )
    context_text = "\n\n".join(chunks) if chunks else "нет"
    return {
        "judge_system_prompt": RAG_EVAL_JUDGE_SYSTEM_PROMPT,
        "judge_user_prompt": (
            f"Вопрос:\n{state.get('question', '')}\n\n"
            f"Эталонный ответ или критерии:\n{state.get('expected_answer') or 'нет'}\n\n"
            f"Ответ RAG-агента:\n{state.get('answer_text', '')}\n\n"
            "Найденный контекст:\n"
            f"{context_text}"
        ),
    }


async def _invoke_judge(state: RagEvalJudgeState) -> RagEvalJudgeState:
    db = state.get("db")
    if db is None:
        return {
            "judge_ok": False,
            "judge_error_message": None,
            "judge_provider_kind": None,
            "judge_model": None,
            "judge_provider_config_id": state.get("provider_config_id"),
            "judge_payload": None,
        }

    result = await LLMRuntimeService.invoke_chat(
        db,
        agent_key=RAG_EVAL_JUDGE_AGENT_KEY,
        actor_user_id=state.get("actor_user_id"),
        task_id=state.get("task_id"),
        project_id=state.get("project_id"),
        system_prompt=str(state.get("judge_system_prompt", "")),
        user_prompt=str(state.get("judge_user_prompt", "")),
        prompt_key=RAG_EVAL_JUDGE_AGENT_KEY,
        provider_config_id=state.get("provider_config_id"),
    )
    return {
        "judge_ok": bool(result.ok),
        "judge_error_message": result.error_message,
        "judge_provider_kind": result.provider_kind,
        "judge_model": result.model,
        "judge_provider_config_id": result.provider_config_id,
        "judge_payload": _extract_json_payload(result.text or "")
        if result.ok and result.text
        else None,
    }


def _finalize_judge(state: RagEvalJudgeState) -> RagEvalJudgeState:
    payload = state.get("judge_payload") if state.get("judge_ok") else None
    if not isinstance(payload, dict):
        payload = {
            "groundedness": "unsupported",
            "correctness": "not_enough_context",
            "unsupported_claims": [],
            "rationale": state.get("judge_error_message") or "Judge did not return valid JSON.",
        }

    groundedness = str(payload.get("groundedness") or "unsupported")
    if groundedness not in {"grounded", "partially_grounded", "unsupported"}:
        groundedness = "unsupported"
    correctness = str(payload.get("correctness") or "not_enough_context")
    if correctness not in {"correct", "partially_correct", "incorrect", "not_enough_context"}:
        correctness = "not_enough_context"
    claims = payload.get("unsupported_claims")
    return {
        "judge_payload": {
            "groundedness": groundedness,
            "correctness": correctness,
            "unsupported_claims": [str(item) for item in claims]
            if isinstance(claims, list)
            else [],
            "rationale": str(payload.get("rationale") or ""),
            "provider_config_id": state.get("judge_provider_config_id"),
            "provider_kind": state.get("judge_provider_kind"),
            "model": state.get("judge_model"),
            "ok": bool(state.get("judge_ok")),
        }
    }


@lru_cache
def get_rag_eval_judge_graph():
    graph = StateGraph(RagEvalJudgeState)
    graph.add_node(
        "prepare_judge_prompt", traced_node("prepare_judge_prompt", _prepare_judge_prompt)
    )
    graph.add_node("invoke_judge", traced_node("invoke_judge", _invoke_judge))
    graph.add_node("finalize_judge", traced_node("finalize_judge", _finalize_judge))
    graph.add_edge(START, "prepare_judge_prompt")
    graph.add_edge("prepare_judge_prompt", "invoke_judge")
    graph.add_edge("invoke_judge", "finalize_judge")
    graph.add_edge("finalize_judge", END)
    return graph.compile()


async def run_rag_eval_judge_graph(
    *,
    db: Any,
    actor_user_id: str | None,
    task_id: str | None,
    project_id: str | None,
    question: str,
    expected_answer: str | None,
    answer_text: str,
    retrieved_chunks: list[dict[str, object]],
    provider_config_id: str | None = None,
) -> RagEvalJudgeState:
    state = await run_traced_graph(
        graph_key="rag_eval_judge_graph",
        graph=get_rag_eval_judge_graph(),
        source="rag_eval",
        input_state={
            "db": db,
            "actor_user_id": actor_user_id,
            "task_id": task_id,
            "project_id": project_id,
            "question": question,
            "expected_answer": expected_answer,
            "answer_text": answer_text,
            "retrieved_chunks": retrieved_chunks,
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
    }
