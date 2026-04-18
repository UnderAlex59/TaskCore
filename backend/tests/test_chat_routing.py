from __future__ import annotations

from app.agents.chat_routing import message_relates_to_task_context


def test_team_coordination_smalltalk_is_not_treated_as_task_question() -> None:
    assert (
        message_relates_to_task_context(
            task_title="Синхронизация статусов заказа",
            task_content=(
                "Система должна сохранять новый статус заказа, публиковать событие "
                "в шину и обновлять интерфейс после перезагрузки."
            ),
            message_content="Как настроение, гтовы поработать над задачей?\n\n",
        )
        is False
    )


def test_specific_requirement_question_is_still_treated_as_task_context() -> None:
    assert (
        message_relates_to_task_context(
            task_title="Синхронизация статусов заказа",
            task_content=(
                "Система должна сохранять новый статус заказа, публиковать событие "
                "в шину и обновлять интерфейс после перезагрузки."
            ),
            message_content=(
                "Какой статус должен уйти в шину событий после обновления заказа?"
            ),
        )
        is True
    )
