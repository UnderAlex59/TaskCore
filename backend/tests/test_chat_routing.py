from __future__ import annotations

from app.agents.chat_routing import normalize_chat_routing_decision


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
