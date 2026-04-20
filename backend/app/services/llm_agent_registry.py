from __future__ import annotations

from functools import lru_cache

from app.agents.change_tracker_agent_graph import (
    CHANGE_TRACKER_AGENT_ALIASES,
    CHANGE_TRACKER_AGENT_DESCRIPTION,
    CHANGE_TRACKER_AGENT_KEY,
    CHANGE_TRACKER_AGENT_NAME,
)
from app.agents.chat_agents.base import ChatAgentMetadata
from app.agents.chat_routing import (
    CHAT_ROUTING_AGENT_ALIASES,
    CHAT_ROUTING_AGENT_DESCRIPTION,
    CHAT_ROUTING_AGENT_KEY,
    CHAT_ROUTING_AGENT_NAME,
)
from app.agents.qa_agent_graph import (
    QA_AGENT_ALIASES,
    QA_AGENT_DESCRIPTION,
    QA_AGENT_KEY,
    QA_AGENT_NAME,
)
from app.agents.validation_graph import (
    VALIDATION_AGENT_ALIASES,
    VALIDATION_AGENT_DESCRIPTION,
    VALIDATION_AGENT_KEY,
    VALIDATION_AGENT_NAME,
)


@lru_cache
def list_llm_agents() -> tuple[ChatAgentMetadata, ...]:
    return (
        ChatAgentMetadata(
            key=QA_AGENT_KEY,
            name=QA_AGENT_NAME,
            description=QA_AGENT_DESCRIPTION,
            aliases=QA_AGENT_ALIASES,
            priority=20,
        ),
        ChatAgentMetadata(
            key=CHANGE_TRACKER_AGENT_KEY,
            name=CHANGE_TRACKER_AGENT_NAME,
            description=CHANGE_TRACKER_AGENT_DESCRIPTION,
            aliases=CHANGE_TRACKER_AGENT_ALIASES,
            priority=30,
        ),
        ChatAgentMetadata(
            key=CHAT_ROUTING_AGENT_KEY,
            name=CHAT_ROUTING_AGENT_NAME,
            description=CHAT_ROUTING_AGENT_DESCRIPTION,
            aliases=CHAT_ROUTING_AGENT_ALIASES,
            priority=40,
        ),
        ChatAgentMetadata(
            key=VALIDATION_AGENT_KEY,
            name=VALIDATION_AGENT_NAME,
            description=VALIDATION_AGENT_DESCRIPTION,
            aliases=VALIDATION_AGENT_ALIASES,
            priority=50,
        ),
    )
