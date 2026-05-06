from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.graph_run_event import GraphRunEvent
from app.models.graph_run_log import GraphRunLog
from app.models.llm_runtime_settings import LLMRuntimeSettings

GRAPH_RUN_CONTEXT: ContextVar[str | None] = ContextVar("graph_run_id", default=None)
GRAPH_NODE_CONTEXT: ContextVar[str | None] = ContextVar("graph_node_name", default=None)
GRAPH_TRACE_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar(
    "graph_trace_context",
    default=None,
)

MAX_PREVIEW_TEXT_CHARS = 4000
MAX_PREVIEW_ITEMS = 30
MAX_PREVIEW_DEPTH = 5
TRUNCATED = "[truncated]"
OMITTED = "[omitted]"
SENSITIVE_KEY_MARKERS = ("secret", "token", "password", "api_key", "authorization", "image_bytes")

StateT = TypeVar("StateT")


def get_current_graph_run_id() -> str | None:
    return GRAPH_RUN_CONTEXT.get()


def get_current_graph_node_name() -> str | None:
    return GRAPH_NODE_CONTEXT.get()


def _current_trace() -> dict[str, Any] | None:
    return GRAPH_TRACE_CONTEXT.get()


def _current_namespace() -> str | None:
    trace = _current_trace()
    if trace is None:
        return None
    graph_stack = trace.get("graph_stack")
    if not isinstance(graph_stack, list) or not graph_stack:
        return None
    return " / ".join(str(item) for item in graph_stack if str(item))


def _current_graph_key() -> str | None:
    trace = _current_trace()
    if trace is None:
        return None
    graph_stack = trace.get("graph_stack")
    if not isinstance(graph_stack, list) or not graph_stack:
        return None
    return str(graph_stack[-1])


def _next_sequence(trace: dict[str, Any]) -> int:
    sequence = int(trace.get("sequence", 0)) + 1
    trace["sequence"] = sequence
    return sequence


def traced_node(
    name: str,
    func: Callable[[StateT], StateT | Awaitable[StateT]],
) -> Callable[[StateT], Any]:
    async def wrapper(state: StateT) -> StateT:
        trace = _current_trace()
        token = GRAPH_NODE_CONTEXT.set(name)
        started = perf_counter()
        input_preview = safe_preview(state)
        try:
            result = func(state)
            if inspect.isawaitable(result):
                result = await result
            result_preview = safe_preview(result)
            if trace is not None:
                await _append_event(
                    run_id=str(trace["run_id"]),
                    sequence=_next_sequence(trace),
                    event_type="node",
                    namespace=_current_namespace(),
                    payload={
                        "graph_key": _current_graph_key(),
                        "input": input_preview,
                        "input_preview": input_preview,
                        "node_name": name,
                        "result": result_preview,
                        "result_preview": result_preview,
                    },
                    status="success",
                    latency_ms=int((perf_counter() - started) * 1000),
                    node_name=name,
                    error_message=None,
                )
            return result  # type: ignore[return-value]
        except Exception as exc:
            if trace is not None:
                await _append_event(
                    run_id=str(trace["run_id"]),
                    sequence=_next_sequence(trace),
                    event_type="node",
                    namespace=_current_namespace(),
                    payload={
                        "graph_key": _current_graph_key(),
                        "input": input_preview,
                        "input_preview": input_preview,
                        "node_name": name,
                        "result": None,
                        "result_preview": None,
                    },
                    status="error",
                    latency_ms=int((perf_counter() - started) * 1000),
                    node_name=name,
                    error_message=str(exc),
                )
            raise
        finally:
            GRAPH_NODE_CONTEXT.reset(token)

    return wrapper


def traced_condition(
    name: str,
    source_node: str,
    path_map: dict[Any, str],
    func: Callable[[StateT], Any],
) -> Callable[[StateT], Any]:
    async def wrapper(state: StateT) -> Any:
        result = func(state)
        if inspect.isawaitable(result):
            result = await result
        trace = _current_trace()
        if trace is not None:
            selected_values = list(result) if isinstance(result, list | tuple | set) else [result]
            targets = [path_map.get(value, str(value)) for value in selected_values]
            selected_text = [str(value) for value in selected_values]
            target_text = [str(target) for target in targets]
            await _append_event(
                run_id=str(trace["run_id"]),
                sequence=_next_sequence(trace),
                event_type="transition",
                namespace=_current_namespace(),
                payload={
                    "condition": name,
                    "condition_input_preview": safe_preview(state),
                    "graph_key": _current_graph_key(),
                    "reason": ", ".join(selected_text),
                    "source_node": source_node,
                    "selected": selected_text,
                    "target_nodes": target_text,
                },
                status="success",
                latency_ms=None,
                node_name=source_node,
                error_message=None,
            )
        return result

    return wrapper


def safe_preview(value: Any, *, depth: int = 0) -> Any:
    if depth > MAX_PREVIEW_DEPTH:
        return TRUNCATED
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, bytes | bytearray | memoryview):
        return f"{OMITTED}: binary {len(value)} bytes"
    if isinstance(value, str):
        if len(value) <= MAX_PREVIEW_TEXT_CHARS:
            return value
        return f"{value[:MAX_PREVIEW_TEXT_CHARS]}...{TRUNCATED}"
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        preview: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= MAX_PREVIEW_ITEMS:
                preview["__truncated__"] = True
                break
            key_text = str(key)
            if any(marker in key_text.casefold() for marker in SENSITIVE_KEY_MARKERS):
                preview[key_text] = OMITTED
                continue
            if key_text == "db":
                preview[key_text] = OMITTED
                continue
            preview[key_text] = safe_preview(item, depth=depth + 1)
        return preview
    if isinstance(value, list | tuple | set):
        items = list(value)
        preview = [safe_preview(item, depth=depth + 1) for item in items[:MAX_PREVIEW_ITEMS]]
        if len(items) > MAX_PREVIEW_ITEMS:
            preview.append(TRUNCATED)
        return preview
    return str(value)[:MAX_PREVIEW_TEXT_CHARS]


def _extract_context(input_state: dict[str, Any], source: str | None) -> dict[str, str | None]:
    return {
        "actor_user_id": _optional_str(input_state.get("actor_user_id")),
        "project_id": _optional_str(input_state.get("project_id")),
        "task_id": _optional_str(input_state.get("task_id")),
        "source": source,
    }


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_stream_part(part: Any) -> tuple[str, str | None, Any]:
    namespace: str | None = None
    mode = "unknown"
    payload = part
    if isinstance(part, tuple):
        if len(part) == 2:
            mode, payload = str(part[0]), part[1]
        elif len(part) == 3:
            namespace = _format_namespace(part[0])
            mode, payload = str(part[1]), part[2]
    return mode, namespace, payload


def _format_namespace(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, tuple | list):
        return " / ".join(str(item) for item in value)
    return str(value)


def _extract_node_name(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key in ("name", "node", "node_name"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
        if len(payload) == 1:
            only_key = next(iter(payload.keys()))
            if isinstance(only_key, str):
                return only_key
    return None


def _extract_status(mode: str, payload: Any) -> str:
    if isinstance(payload, dict):
        status = payload.get("status") or payload.get("state")
        if isinstance(status, str) and status:
            normalized = status.casefold()
            if "error" in normalized or "fail" in normalized:
                return "error"
            if "success" in normalized or "finish" in normalized or "complete" in normalized:
                return "success"
            if "start" in normalized:
                return "running"
    if mode in {"values", "updates", "debug", "tasks"}:
        return "success"
    return "success"


def _extract_error(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key in ("error", "exception", "error_message"):
            value = payload.get(key)
            if value:
                return str(value)[:1000]
    return None


async def _create_run(
    *,
    graph_key: str,
    input_state: dict[str, Any],
    source: str | None,
) -> str:
    context = _extract_context(input_state, source)
    run = GraphRunLog(
        graph_key=graph_key,
        status="running",
        actor_user_id=context["actor_user_id"],
        project_id=context["project_id"],
        task_id=context["task_id"],
        source=context["source"],
        input_preview=safe_preview(input_state),
    )
    async with AsyncSessionLocal() as db:
        db.add(run)
        await db.commit()
    return run.id


async def _append_event(
    *,
    run_id: str,
    sequence: int,
    event_type: str,
    namespace: str | None,
    payload: Any,
    status: str | None = None,
    latency_ms: int | None = None,
    node_name: str | None = None,
    error_message: str | None = None,
) -> None:
    db_payload = safe_preview(payload)
    event = GraphRunEvent(
        graph_run_id=run_id,
        sequence=sequence,
        event_type=event_type,
        node_name=node_name or _extract_node_name(payload),
        namespace=namespace,
        status=status or _extract_status(event_type, payload),
        finished_at=datetime.now(timezone.utc),
        latency_ms=latency_ms,
        payload=db_payload if isinstance(db_payload, dict) else {"value": db_payload},
        error_message=error_message or _extract_error(payload),
    )
    async with AsyncSessionLocal() as db:
        db.add(event)
        await db.commit()


async def _finish_run(
    *,
    run_id: str,
    status: str,
    started: float,
    final_state: Any,
    error_message: str | None,
) -> None:
    async with AsyncSessionLocal() as db:
        run = await db.get(GraphRunLog, run_id)
        if run is None:
            return
        run.status = status
        run.finished_at = datetime.now(timezone.utc)
        run.latency_ms = int((perf_counter() - started) * 1000)
        run.error_message = error_message[:1000] if error_message else None
        final_preview = safe_preview(final_state)
        run.final_state_preview = (
            final_preview if isinstance(final_preview, dict) else {"value": final_preview}
        )
        await db.commit()


async def _stream_graph(graph: Any, input_state: dict[str, Any]):
    stream_kwargs = {
        "stream_mode": "values",
    }
    async for part in graph.astream(input_state, **stream_kwargs):
        yield part


async def _is_graph_monitoring_enabled(input_state: dict[str, Any]) -> bool:
    if not get_settings().GRAPH_RUN_MONITORING_ENABLED:
        return False
    db = input_state.get("db")
    if isinstance(db, AsyncSession):
        runtime_settings = await db.get(LLMRuntimeSettings, 1)
        if runtime_settings is not None:
            return bool(runtime_settings.graph_monitoring_enabled)
    return True


def _push_graph_context(graph_key: str) -> int:
    trace = _current_trace()
    if trace is None:
        return 0
    graph_stack = trace.setdefault("graph_stack", [])
    if not isinstance(graph_stack, list):
        trace["graph_stack"] = []
        graph_stack = trace["graph_stack"]
    parent_node = GRAPH_NODE_CONTEXT.get()
    additions = [parent_node, graph_key] if parent_node else [graph_key]
    graph_stack.extend(str(item) for item in additions if item)
    return len(additions)


def _pop_graph_context(count: int) -> None:
    trace = _current_trace()
    if trace is None or count <= 0:
        return
    graph_stack = trace.get("graph_stack")
    if not isinstance(graph_stack, list):
        return
    del graph_stack[-count:]


async def run_traced_graph(
    *,
    graph_key: str,
    graph: Any,
    input_state: dict[str, Any],
    source: str | None = None,
) -> Any:
    existing_trace = _current_trace()
    has_db = isinstance(input_state.get("db"), AsyncSession)
    monitoring_enabled = (
        True if existing_trace is not None else await _is_graph_monitoring_enabled(input_state)
    )
    if existing_trace is None and (not has_db or not monitoring_enabled):
        final_state: Any = None
        async for part in _stream_graph(graph, input_state):
            mode, _, payload = _normalize_stream_part(part)
            if mode in {"values", "unknown"}:
                final_state = payload
        return final_state or {}

    created_top_level_run = existing_trace is None
    run_id = (
        await _create_run(graph_key=graph_key, input_state=input_state, source=source)
        if created_top_level_run
        else str(existing_trace["run_id"])
    )
    run_token = None
    trace_token = None
    if created_top_level_run:
        run_token = GRAPH_RUN_CONTEXT.set(run_id)
        trace_token = GRAPH_TRACE_CONTEXT.set(
            {
                "graph_stack": [],
                "run_id": run_id,
                "sequence": 0,
            }
        )
    pushed_count = _push_graph_context(graph_key)
    started = perf_counter()
    final_state: Any = {}
    try:
        async for part in _stream_graph(graph, input_state):
            mode, _, payload = _normalize_stream_part(part)
            if mode in {"values", "unknown"}:
                final_state = payload
        if created_top_level_run:
            await _finish_run(
                run_id=run_id,
                status="success",
                started=started,
                final_state=final_state,
                error_message=None,
            )
        return final_state
    except Exception as exc:
        if created_top_level_run:
            await _finish_run(
                run_id=run_id,
                status="error",
                started=started,
                final_state=final_state,
                error_message=str(exc),
            )
        raise
    finally:
        _pop_graph_context(pushed_count)
        if trace_token is not None:
            GRAPH_TRACE_CONTEXT.reset(trace_token)
        if run_token is not None:
            GRAPH_RUN_CONTEXT.reset(run_token)
