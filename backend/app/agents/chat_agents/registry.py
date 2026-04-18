from __future__ import annotations

import importlib
import pkgutil
import re
from functools import lru_cache

from app.core.config import get_settings

from .base import BaseChatAgent, ChatAgentContext, ChatAgentMetadata, ChatAgentResult

_CHAT_AGENT_PACKAGE = "app.agents.chat_agents"
_REQUESTED_AGENT_PATTERN = re.compile(
    r"^(?:@|/)(?P<agent>[a-z0-9][a-z0-9_-]*)\s+(?P<content>.+)$",
    re.IGNORECASE,
)
_REGISTERED_AGENT_TYPES: dict[str, type[BaseChatAgent]] = {}


def register_chat_agent(agent_type: type[BaseChatAgent]) -> type[BaseChatAgent]:
    key = agent_type.metadata.key.casefold()
    existing = _REGISTERED_AGENT_TYPES.get(key)
    if existing is not None and existing is not agent_type:
        raise ValueError(f"Chat agent '{agent_type.metadata.key}' is already registered")
    _REGISTERED_AGENT_TYPES[key] = agent_type
    return agent_type


def parse_requested_agent(message_content: str) -> tuple[str | None, str]:
    stripped = message_content.strip()
    match = _REQUESTED_AGENT_PATTERN.match(stripped)
    if match is None:
        return None, stripped

    requested_agent = match.group("agent").casefold()
    routed_content = match.group("content").strip()
    return requested_agent, routed_content


def _discover_builtin_agents() -> None:
    package = importlib.import_module(_CHAT_AGENT_PACKAGE)
    package_path = getattr(package, "__path__", [])
    prefix = f"{_CHAT_AGENT_PACKAGE}."
    skip_modules = {"base", "registry"}
    for module_info in pkgutil.iter_modules(package_path, prefix):
        module_name = module_info.name.rsplit(".", maxsplit=1)[-1]
        if module_name in skip_modules:
            continue
        importlib.import_module(module_info.name)


def _import_configured_agent_modules() -> None:
    settings = get_settings()
    for module_path in settings.CHAT_AGENT_MODULES:
        importlib.import_module(module_path)


@lru_cache
def get_chat_agents() -> tuple[BaseChatAgent, ...]:
    _discover_builtin_agents()
    _import_configured_agent_modules()
    agents = (agent_type() for agent_type in _REGISTERED_AGENT_TYPES.values())
    return tuple(sorted(agents, key=lambda agent: agent.metadata.priority))


def list_chat_agents() -> tuple[ChatAgentMetadata, ...]:
    return tuple(agent.metadata for agent in get_chat_agents())


def reset_chat_agent_registry() -> None:
    get_chat_agents.cache_clear()


def _find_chat_agent(requested_agent: str) -> BaseChatAgent | None:
    for agent in get_chat_agents():
        if agent.supports_key(requested_agent):
            return agent
    return None


def _available_agents_payload() -> list[dict[str, str]]:
    return [{"key": item.key, "name": item.name} for item in list_chat_agents()]


def _enrich_result(
    result: ChatAgentResult,
    agent: BaseChatAgent,
    *,
    routing_mode: str,
) -> ChatAgentResult:
    source_ref = dict(result.source_ref)
    source_ref.setdefault("agent_key", agent.metadata.key)
    source_ref.setdefault("agent_description", agent.metadata.description)
    source_ref.setdefault("routing_mode", routing_mode)
    return ChatAgentResult(
        agent_name=result.agent_name,
        message_type=result.message_type,
        response=result.response,
        source_ref=source_ref,
        proposal_text=result.proposal_text,
    )


def _unknown_agent_result(requested_agent: str) -> ChatAgentResult:
    available_agents = _available_agents_payload()
    available_keys = ", ".join(item["key"] for item in available_agents)
    return ChatAgentResult(
        agent_name="ManagerAgent",
        message_type="agent_answer",
        response=(
            f"Agent '{requested_agent}' не зарегистрирован. "
            f"Доступные агенты: {available_keys}."
        ),
        source_ref={
            "collection": "messages",
            "routing_mode": "forced",
            "requested_agent": requested_agent,
            "available_agents": available_agents,
        },
    )


async def dispatch_chat_agent(context: ChatAgentContext) -> ChatAgentResult:
    if context.requested_agent is not None:
        selected_agent = _find_chat_agent(context.requested_agent)
        if selected_agent is None:
            return _unknown_agent_result(context.requested_agent)
        result = await selected_agent.handle(context)
        return _enrich_result(result, selected_agent, routing_mode="forced")

    for agent in get_chat_agents():
        if await agent.can_handle(context):
            result = await agent.handle(context)
            return _enrich_result(result, agent, routing_mode="auto")

    raise RuntimeError("Нет доступных chat-агентов для обработки сообщения")
