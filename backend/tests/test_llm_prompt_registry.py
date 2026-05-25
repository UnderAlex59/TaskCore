from __future__ import annotations

from app.services.llm_prompt_registry import list_llm_prompt_definitions

REQUIRED_KEYS_BY_PROMPT = {
    "qa-answer": (
        "answer",
        "confidence",
        "canonical_question",
        "used_cross_task_chunk_ids",
    ),
    "qa-verifier": (
        "final_answer",
        "confidence",
        "grounded",
        "canonical_question",
        "used_cross_task_chunk_ids",
    ),
    "rag-eval-judge": (
        "groundedness",
        "correctness",
        "unsupported_claims",
        "rationale",
    ),
    "validation-eval-question-judge": (
        "relevance",
        "specificity",
        "actionability",
        "novelty",
        "rationale",
    ),
    "adaptation-eval-match-judge": (
        "matches",
        "unmatched_expected_indices",
        "unmatched_actual_indices",
        "ok",
    ),
    "qure-eval-weak-word-judge": (
        "passed",
        "score",
        "verdict_match",
        "weak_word_match",
        "matched_issue_indices",
        "rationale",
    ),
    "change-tracker": ("proposal_text", "acknowledgement"),
    "chat-routing": (
        "ai_response_required",
        "target_agent_key",
        "message_type",
        "reason",
    ),
    "task-validation-core": ("issues", "questions", "code", "severity", "message"),
    "task-validation-custom-rules": ("issues", "code", "severity", "message"),
    "task-validation-context-questions": ("questions",),
}


def test_registered_default_prompts_define_json_contracts() -> None:
    definitions = list_llm_prompt_definitions()

    assert definitions
    for definition in definitions:
        prompt = definition.default_system_prompt
        assert "JSON" in prompt
        for key in REQUIRED_KEYS_BY_PROMPT[definition.prompt_key]:
            assert key in prompt


def test_default_prompts_pin_parser_enum_values() -> None:
    prompts = {
        item.prompt_key: item.default_system_prompt
        for item in list_llm_prompt_definitions()
    }

    for prompt_key in ("qa-answer", "qa-verifier"):
        prompt = prompts[prompt_key]
        assert '"high"' in prompt
        assert '"low"' in prompt
        assert '"medium"' not in prompt

    routing_prompt = prompts["chat-routing"]
    assert '"general"' in routing_prompt
    assert '"question"' in routing_prompt
    assert '"change_proposal"' in routing_prompt

    for prompt_key in ("task-validation-core", "task-validation-custom-rules"):
        prompt = prompts[prompt_key]
        assert '"low"' in prompt
        assert '"medium"' in prompt
        assert '"high"' in prompt


def test_default_prompts_do_not_request_chain_of_thought() -> None:
    forbidden_phrases = (
        "think step by step",
        "chain of thought",
        "рассуждай пошагово",
        "раскрой рассуждения",
        "покажи рассуждения",
    )

    for definition in list_llm_prompt_definitions():
        prompt = definition.default_system_prompt.casefold()
        for phrase in forbidden_phrases:
            assert phrase not in prompt


def test_few_shot_examples_are_limited_to_complex_prompts() -> None:
    prompts = {
        item.prompt_key: item.default_system_prompt
        for item in list_llm_prompt_definitions()
    }

    for prompt_key in (
        "chat-routing",
        "change-tracker",
        "task-validation-context-questions",
        "adaptation-eval-match-judge",
        "qure-eval-weak-word-judge",
    ):
        assert "Примеры" in prompts[prompt_key]

    for prompt_key in (
        "qa-answer",
        "qa-verifier",
        "rag-eval-judge",
        "validation-eval-question-judge",
        "task-validation-core",
        "task-validation-custom-rules",
    ):
        assert "Примеры" not in prompts[prompt_key]
