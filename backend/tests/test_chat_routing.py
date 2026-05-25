from __future__ import annotations

from app.agents.chat_routing import normalize_chat_routing_decision
from app.agents.system_prompts import CHAT_ROUTING_SYSTEM_PROMPT


def test_routing_decision_accepts_registered_agent() -> None:
    outcome, error = normalize_chat_routing_decision(
        {
            "ai_response_required": True,
            "target_agent_key": "qa",
            "message_type": "question",
            "reason": "Вопрос по требованиям задачи.",
        },
        available_agent_keys={"qa", "change-tracker"},
    )

    assert error is None
    assert outcome is not None
    assert outcome.ai_response_required is True
    assert outcome.target_agent_key == "qa"
    assert outcome.message_type == "question"


def test_routing_decision_skips_without_agent() -> None:
    outcome, error = normalize_chat_routing_decision(
        {
            "ai_response_required": False,
            "target_agent_key": None,
            "message_type": "general",
            "reason": "Small talk вне задачи.",
        },
        available_agent_keys={"qa", "change-tracker"},
    )

    assert error is None
    assert outcome is not None
    assert outcome.ai_response_required is False
    assert outcome.target_agent_key is None
    assert outcome.status == "skipped"


def test_routing_decision_canonicalizes_agent_alias() -> None:
    outcome, error = normalize_chat_routing_decision(
        {
            "ai_response_required": True,
            "target_agent_key": "QA-Agent",
            "message_type": "question",
            "reason": "Вопрос по требованиям задачи.",
        },
        available_agent_keys={"qa", "change-tracker"},
        available_agents=[
            {
                "key": "qa",
                "name": "QAAgent",
                "description": "Отвечает на вопросы.",
                "aliases": ["question", "qa-agent"],
            },
            {
                "key": "change-tracker",
                "name": "ChangeTrackerAgent",
                "description": "Готовит предложения изменений.",
                "aliases": ["change", "proposal"],
            },
        ],
    )

    assert error is None
    assert outcome is not None
    assert outcome.target_agent_key == "qa"
    assert outcome.message_type == "question"


def test_routing_decision_falls_back_to_message_type_for_invalid_agent_key() -> None:
    outcome, error = normalize_chat_routing_decision(
        {
            "ai_response_required": True,
            "target_agent_key": "change-proposal",
            "message_type": "change_proposal",
            "reason": "Пользователь предлагает отказаться от выполнения задачи.",
        },
        available_agent_keys={"qa", "change-tracker"},
    )

    assert error is None
    assert outcome is not None
    assert outcome.target_agent_key == "change-tracker"
    assert outcome.message_type == "change_proposal"


def test_routing_decision_rejects_unregistered_agent() -> None:
    outcome, error = normalize_chat_routing_decision(
        {
            "ai_response_required": True,
            "target_agent_key": "risk",
            "message_type": "general",
            "reason": "Нужен risk agent.",
        },
        available_agent_keys={"qa", "change-tracker"},
    )

    assert outcome is None
    assert error == "invalid_target_agent_key"


def test_chat_routing_prompt_forbids_unregistered_agent_keys() -> None:
    assert "Никогда не возвращай target_agent_key" in CHAT_ROUTING_SYSTEM_PROMPT
    assert "которого нет в списке доступных агентов" in CHAT_ROUTING_SYSTEM_PROMPT
    assert '"general"' in CHAT_ROUTING_SYSTEM_PROMPT
    assert '"question"' in CHAT_ROUTING_SYSTEM_PROMPT
    assert '"change_proposal"' in CHAT_ROUTING_SYSTEM_PROMPT
