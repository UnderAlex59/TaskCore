"""Business logic services."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "AuthService",
    "ChatService",
    "ProjectService",
    "ProposalService",
    "RagService",
    "TaskService",
    "UserService",
]

_SERVICE_MODULES = {
    "AuthService": "app.services.auth_service",
    "ChatService": "app.services.chat_service",
    "ProjectService": "app.services.project_service",
    "ProposalService": "app.services.proposal_service",
    "RagService": "app.services.rag_service",
    "TaskService": "app.services.task_service",
    "UserService": "app.services.user_service",
}


def __getattr__(name: str):
    module_path = _SERVICE_MODULES.get(name)
    if module_path is None:
        raise AttributeError(name)
    module = import_module(module_path)
    return getattr(module, name)
