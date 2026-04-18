from __future__ import annotations

from typing import Any

VALIDATION_NODE_KEYS = (
    "core_rules",
    "custom_rules",
    "context_questions",
)

DEFAULT_VALIDATION_NODE_SETTINGS: dict[str, bool] = {
    "core_rules": True,
    "custom_rules": True,
    "context_questions": True,
}


def normalize_validation_node_settings(settings: dict[str, Any] | None) -> dict[str, bool]:
    normalized = dict(DEFAULT_VALIDATION_NODE_SETTINGS)
    if not settings:
        return normalized

    for key in VALIDATION_NODE_KEYS:
        if key in settings:
            normalized[key] = bool(settings[key])
    return normalized
