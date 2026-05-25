from app.services.proposal_service import ProposalService


def test_accepted_change_is_appended_to_history_section() -> None:
    content = "## Описание\nSaved report filters remain available after refresh."

    updated_content = ProposalService._append_accepted_change_to_history(
        content,
        "Add an explicit reviewer approval step.",
    )

    assert updated_content == (
        "## Описание\nSaved report filters remain available after refresh.\n\n"
        "## История изменений\n"
        "- Add an explicit reviewer approval step."
    )


def test_accepted_change_uses_existing_history_section() -> None:
    content = "## Описание\nSaved report filters.\n\n## История изменений\n- Initial approval."

    updated_content = ProposalService._append_accepted_change_to_history(
        content,
        "Add an explicit reviewer approval step.",
    )

    assert updated_content == (
        "## Описание\nSaved report filters.\n\n"
        "## История изменений\n"
        "- Initial approval.\n"
        "- Add an explicit reviewer approval step."
    )


def test_accepted_change_is_added_to_history_when_present_in_body_only() -> None:
    content = (
        "## Описание\n"
        "Saved report filters. Add an explicit reviewer approval step."
    )

    updated_content = ProposalService._append_accepted_change_to_history(
        content,
        "Add an explicit reviewer approval step.",
    )

    assert updated_content == (
        "## Описание\n"
        "Saved report filters. Add an explicit reviewer approval step.\n\n"
        "## История изменений\n"
        "- Add an explicit reviewer approval step."
    )


def test_accepted_change_is_not_duplicated_from_legacy_history_section() -> None:
    content = (
        "## Описание\nSaved report filters.\n\n"
        "## Одобренные изменения\n"
        "- Add an explicit reviewer approval step."
    )

    updated_content = ProposalService._append_accepted_change_to_history(
        content,
        "Add an explicit reviewer approval step.",
    )

    assert updated_content == content
