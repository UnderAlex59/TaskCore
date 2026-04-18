from __future__ import annotations

import importlib
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.agents.chat_agents.base import ChatAgentContext, ChatAgentMetadata
from app.agents.chat_agents.llm import ChatAgentLLMProfile
from app.agents.chat_routing import message_relates_to_task_context
from app.agents.state import ChatState
from app.core.config import get_settings

AgentSubgraphCanHandle = Callable[[ChatAgentContext], bool | Awaitable[bool]]
AgentSubgraphRunner = Callable[[ChatAgentContext, str], Awaitable[ChatState]]
AgentGraphFactory = Callable[[], Any]

_REGISTERED_AGENT_SUBGRAPHS: dict[str, AgentSubgraphSpec] = {}
_BUILTIN_SUBGRAPHS_REGISTERED = False


@dataclass(frozen=True, slots=True)
class AgentSubgraphSpec:
    metadata: ChatAgentMetadata
    runner: AgentSubgraphRunner
    can_handle: AgentSubgraphCanHandle | None = None
    graph_factory: AgentGraphFactory | None = None
    llm_profile: ChatAgentLLMProfile | None = None
    auto_routable: bool = True

    def supports_key(self, key: str) -> bool:
        normalized_key = key.casefold()
        aliases = {alias.casefold() for alias in self.metadata.aliases}
        return normalized_key == self.metadata.key.casefold() or normalized_key in aliases


def register_agent_subgraph(spec: AgentSubgraphSpec) -> AgentSubgraphSpec:
    key = spec.metadata.key.casefold()
    existing = _REGISTERED_AGENT_SUBGRAPHS.get(key)
    if existing is not None and existing is not spec:
        raise ValueError(f"Agent subgraph '{spec.metadata.key}' is already registered")
    _REGISTERED_AGENT_SUBGRAPHS[key] = spec
    get_agent_subgraphs.cache_clear()
    return spec


def reset_agent_subgraph_registry() -> None:
    global _BUILTIN_SUBGRAPHS_REGISTERED
    _REGISTERED_AGENT_SUBGRAPHS.clear()
    _BUILTIN_SUBGRAPHS_REGISTERED = False
    get_agent_subgraphs.cache_clear()


async def _invoke_can_handle(spec: AgentSubgraphSpec, context: ChatAgentContext) -> bool:
    if not spec.auto_routable or spec.can_handle is None:
        return False

    result = spec.can_handle(context)
    if inspect.isawaitable(result):
        return bool(await result)
    return bool(result)


def _import_configured_subgraph_modules() -> None:
    settings = get_settings()
    for module_path in settings.CHAT_AGENT_MODULES:
        importlib.import_module(module_path)


def _register_builtin_subgraphs() -> None:
    global _BUILTIN_SUBGRAPHS_REGISTERED
    if _BUILTIN_SUBGRAPHS_REGISTERED:
        return

    from app.agents.change_tracker_agent_graph import (
        CHANGE_TRACKER_AGENT_ALIASES,
        CHANGE_TRACKER_AGENT_DESCRIPTION,
        CHANGE_TRACKER_AGENT_KEY,
        CHANGE_TRACKER_AGENT_NAME,
        get_change_tracker_agent_graph,
        run_change_tracker_agent_graph,
    )
    from app.agents.manager_agent_graph import (
        MANAGER_AGENT_ALIASES,
        MANAGER_AGENT_DESCRIPTION,
        MANAGER_AGENT_KEY,
        MANAGER_AGENT_NAME,
        get_manager_agent_graph,
        run_manager_agent_graph,
    )
    from app.agents.qa_agent_graph import (
        QA_AGENT_ALIASES,
        QA_AGENT_DESCRIPTION,
        QA_AGENT_KEY,
        QA_AGENT_NAME,
        get_qa_agent_graph,
        run_qa_agent_graph,
    )

    async def qa_can_handle(context: ChatAgentContext) -> bool:
        return context.message_type == "question" and message_relates_to_task_context(
            task_title=context.task_title,
            task_content=context.task_content,
            message_content=context.message_content,
        )

    async def change_tracker_can_handle(context: ChatAgentContext) -> bool:
        return context.message_type == "change_proposal"

    async def run_qa(context: ChatAgentContext, routing_mode: str) -> ChatState:
        return await run_qa_agent_graph(
            db=context.db,
            actor_user_id=context.actor_user_id,
            task_id=context.task_id,
            project_id=context.project_id,
            task_title=context.task_title,
            task_status=context.task_status,
            task_content=context.task_content,
            message_content=context.message_content,
            validation_result=context.validation_result,
            related_tasks=context.related_tasks,
            routing_mode=routing_mode,
        )

    async def run_change_tracker(context: ChatAgentContext, routing_mode: str) -> ChatState:
        return await run_change_tracker_agent_graph(
            db=context.db,
            actor_user_id=context.actor_user_id,
            task_id=context.task_id,
            project_id=context.project_id,
            task_title=context.task_title,
            task_status=context.task_status,
            task_content=context.task_content,
            message_content=context.message_content,
            routing_mode=routing_mode,
        )

    async def run_manager(context: ChatAgentContext, routing_mode: str) -> ChatState:
        return await run_manager_agent_graph(
            requested_agent=context.requested_agent,
            routing_mode=routing_mode,
        )

    register_agent_subgraph(
        AgentSubgraphSpec(
            metadata=ChatAgentMetadata(
                key=QA_AGENT_KEY,
                name=QA_AGENT_NAME,
                description=QA_AGENT_DESCRIPTION,
                aliases=QA_AGENT_ALIASES,
                priority=20,
            ),
            can_handle=qa_can_handle,
            runner=run_qa,
            graph_factory=get_qa_agent_graph,
            llm_profile=ChatAgentLLMProfile(
                provider="openai",
                model="gpt-4o-mini",
                temperature=0.2,
            ),
        )
    )
    register_agent_subgraph(
        AgentSubgraphSpec(
            metadata=ChatAgentMetadata(
                key=CHANGE_TRACKER_AGENT_KEY,
                name=CHANGE_TRACKER_AGENT_NAME,
                description=CHANGE_TRACKER_AGENT_DESCRIPTION,
                aliases=CHANGE_TRACKER_AGENT_ALIASES,
                priority=30,
            ),
            can_handle=change_tracker_can_handle,
            runner=run_change_tracker,
            graph_factory=get_change_tracker_agent_graph,
            llm_profile=ChatAgentLLMProfile(
                provider="openai",
                model="gpt-4o-mini",
                temperature=0.0,
            ),
        )
    )
    register_agent_subgraph(
        AgentSubgraphSpec(
            metadata=ChatAgentMetadata(
                key=MANAGER_AGENT_KEY,
                name=MANAGER_AGENT_NAME,
                description=MANAGER_AGENT_DESCRIPTION,
                aliases=MANAGER_AGENT_ALIASES,
                priority=1000,
            ),
            can_handle=None,
            runner=run_manager,
            graph_factory=get_manager_agent_graph,
            llm_profile=None,
            auto_routable=False,
        )
    )
    _BUILTIN_SUBGRAPHS_REGISTERED = True


@lru_cache
def get_agent_subgraphs() -> tuple[AgentSubgraphSpec, ...]:
    _register_builtin_subgraphs()
    _import_configured_subgraph_modules()
    return tuple(
        sorted(
            _REGISTERED_AGENT_SUBGRAPHS.values(),
            key=lambda spec: spec.metadata.priority,
        )
    )


def list_agent_subgraphs() -> tuple[AgentSubgraphSpec, ...]:
    return get_agent_subgraphs()


def list_agent_subgraph_metadata() -> tuple[ChatAgentMetadata, ...]:
    return tuple(spec.metadata for spec in get_agent_subgraphs())


def get_exportable_agent_subgraphs() -> tuple[AgentSubgraphSpec, ...]:
    return tuple(spec for spec in get_agent_subgraphs() if spec.graph_factory is not None)


def find_agent_subgraph(key: str) -> AgentSubgraphSpec | None:
    normalized_key = key.casefold()
    for spec in get_agent_subgraphs():
        if spec.supports_key(normalized_key):
            return spec
    return None


async def select_agent_subgraph(context: ChatAgentContext) -> AgentSubgraphSpec | None:
    for spec in get_agent_subgraphs():
        if await _invoke_can_handle(spec, context):
            return spec
    return None


async def run_agent_subgraph(
    spec: AgentSubgraphSpec,
    *,
    context: ChatAgentContext,
    routing_mode: str,
) -> ChatState:
    result = await spec.runner(context, routing_mode)
    source_ref = dict(result.get("source_ref", {}))
    source_ref.setdefault("agent_key", spec.metadata.key)
    source_ref.setdefault("agent_description", spec.metadata.description)
    source_ref.setdefault("routing_mode", routing_mode)

    state: ChatState = {
        "agent_name": str(result.get("agent_name", spec.metadata.name)),
        "message_type": str(result.get("message_type", "agent_answer")),
        "response": str(result.get("response", "")),
        "source_ref": source_ref,
    }
    proposal_text = result.get("proposal_text")
    if proposal_text is not None:
        state["proposal_text"] = str(proposal_text)
    return state
