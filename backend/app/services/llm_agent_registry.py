from __future__ import annotations

from functools import lru_cache

from app.agents.attachment_vision_graph import (
    VISION_AGENT_ALIASES,
    VISION_AGENT_DESCRIPTION,
    VISION_AGENT_KEY,
    VISION_AGENT_NAME,
)
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
    QA_ANSWER_AGENT_ALIASES,
    QA_ANSWER_AGENT_DESCRIPTION,
    QA_ANSWER_AGENT_KEY,
    QA_ANSWER_AGENT_NAME,
    QA_PLANNER_AGENT_ALIASES,
    QA_PLANNER_AGENT_DESCRIPTION,
    QA_PLANNER_AGENT_KEY,
    QA_PLANNER_AGENT_NAME,
    QA_VERIFIER_AGENT_ALIASES,
    QA_VERIFIER_AGENT_DESCRIPTION,
    QA_VERIFIER_AGENT_KEY,
    QA_VERIFIER_AGENT_NAME,
)
from app.agents.task_tag_suggestion_graph import (
    TASK_TAG_SUGGESTER_AGENT_ALIASES,
    TASK_TAG_SUGGESTER_AGENT_DESCRIPTION,
    TASK_TAG_SUGGESTER_AGENT_KEY,
    TASK_TAG_SUGGESTER_AGENT_NAME,
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
            key=QA_PLANNER_AGENT_KEY,
            name=QA_PLANNER_AGENT_NAME,
            description=QA_PLANNER_AGENT_DESCRIPTION,
            aliases=QA_PLANNER_AGENT_ALIASES,
            priority=20,
        ),
        ChatAgentMetadata(
            key=QA_ANSWER_AGENT_KEY,
            name=QA_ANSWER_AGENT_NAME,
            description=QA_ANSWER_AGENT_DESCRIPTION,
            aliases=QA_ANSWER_AGENT_ALIASES,
            priority=30,
        ),
        ChatAgentMetadata(
            key=QA_VERIFIER_AGENT_KEY,
            name=QA_VERIFIER_AGENT_NAME,
            description=QA_VERIFIER_AGENT_DESCRIPTION,
            aliases=QA_VERIFIER_AGENT_ALIASES,
            priority=40,
        ),
        ChatAgentMetadata(
            key=CHANGE_TRACKER_AGENT_KEY,
            name=CHANGE_TRACKER_AGENT_NAME,
            description=CHANGE_TRACKER_AGENT_DESCRIPTION,
            aliases=CHANGE_TRACKER_AGENT_ALIASES,
            priority=50,
        ),
        ChatAgentMetadata(
            key=CHAT_ROUTING_AGENT_KEY,
            name=CHAT_ROUTING_AGENT_NAME,
            description=CHAT_ROUTING_AGENT_DESCRIPTION,
            aliases=CHAT_ROUTING_AGENT_ALIASES,
            priority=60,
        ),
        ChatAgentMetadata(
            key=VALIDATION_AGENT_KEY,
            name=VALIDATION_AGENT_NAME,
            description=VALIDATION_AGENT_DESCRIPTION,
            aliases=VALIDATION_AGENT_ALIASES,
            priority=70,
        ),
        ChatAgentMetadata(
            key=VISION_AGENT_KEY,
            name=VISION_AGENT_NAME,
            description=VISION_AGENT_DESCRIPTION,
            aliases=VISION_AGENT_ALIASES,
            priority=80,
        ),
        ChatAgentMetadata(
            key=TASK_TAG_SUGGESTER_AGENT_KEY,
            name=TASK_TAG_SUGGESTER_AGENT_NAME,
            description=TASK_TAG_SUGGESTER_AGENT_DESCRIPTION,
            aliases=TASK_TAG_SUGGESTER_AGENT_ALIASES,
            priority=90,
        ),
    )
