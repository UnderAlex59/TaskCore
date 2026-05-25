from __future__ import annotations

import re
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.change_tracker_agent_graph import run_change_tracker_agent_graph
from app.agents.chat_routing_eval_graph import run_chat_routing_eval_graph
from app.models.user import User
from app.schemas.admin_change_proposal_eval import (
    ChangeProposalEvalCasePayload,
    ChangeProposalEvalCaseResultRead,
    ChangeProposalEvalRunPayload,
    ChangeProposalEvalRunRead,
    ChangeProposalEvalRunStatus,
)


class AdminChangeProposalEvalService:
    @staticmethod
    def _normalize_text(value: object) -> str:
        return re.sub(r"\s+", " ", str(value or "").casefold()).strip()

    @staticmethod
    def _tokens(value: object) -> set[str]:
        return set(re.findall(r"[A-Za-zА-Яа-яЁё0-9_]{4,}", str(value or "").casefold()))

    @staticmethod
    def _text_matches(expected: object, actual: object, *, threshold: float) -> bool:
        expected_text = AdminChangeProposalEvalService._normalize_text(expected)
        actual_text = AdminChangeProposalEvalService._normalize_text(actual)
        if not expected_text or not actual_text:
            return False
        if (
            expected_text == actual_text
            or expected_text in actual_text
            or actual_text in expected_text
        ):
            return True
        expected_tokens = AdminChangeProposalEvalService._tokens(expected_text)
        actual_tokens = AdminChangeProposalEvalService._tokens(actual_text)
        if not expected_tokens or not actual_tokens:
            return False
        overlap = len(expected_tokens & actual_tokens) / len(expected_tokens | actual_tokens)
        return overlap >= threshold

    @staticmethod
    def _prf(tp: int, fp: int, fn: int) -> dict[str, float]:
        precision = tp / (tp + fp) if tp + fp else (1.0 if fn == 0 else 0.0)
        recall = tp / (tp + fn) if tp + fn else (1.0 if fp == 0 else 0.0)
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }

    @staticmethod
    def _expected(case: ChangeProposalEvalCasePayload) -> dict[str, Any]:
        return {
            "is_proposal": case.expected_is_proposal,
            "proposal_text": case.expected_proposal_text,
            "duplicate": case.expected_duplicate,
            "duplicate_of": case.expected_duplicate_of,
            "action": case.expected_action,
        }

    @staticmethod
    def _actual_action(*, actual_is_proposal: bool, actual_duplicate: bool) -> str:
        if not actual_is_proposal:
            return "ignore"
        if actual_duplicate:
            return "skip_duplicate"
        return "create"

    @staticmethod
    def _case_metrics(
        *,
        case: ChangeProposalEvalCasePayload,
        actual_is_proposal: bool,
        actual_proposal_text: str | None,
        actual_duplicate: bool,
        actual_action: str,
        threshold: float,
    ) -> dict[str, Any]:
        expected_text = case.expected_proposal_text or ""
        text_match = (
            AdminChangeProposalEvalService._text_matches(
                expected_text,
                actual_proposal_text,
                threshold=threshold,
            )
            if case.expected_is_proposal and actual_is_proposal
            else False
        )
        action_match = case.expected_action == actual_action
        duplicate_match = case.expected_duplicate == actual_duplicate
        passed = (
            case.expected_is_proposal == actual_is_proposal
            and action_match
            and duplicate_match
            and (not case.expected_is_proposal or text_match)
        )
        return {
            "passed": passed,
            "proposal_match": case.expected_is_proposal == actual_is_proposal,
            "proposal_text_match": text_match if case.expected_is_proposal else None,
            "duplicate_match": duplicate_match,
            "action_match": action_match,
        }

    @staticmethod
    def _summarize(results: list[ChangeProposalEvalCaseResultRead]) -> dict[str, Any]:
        total = len(results)
        errors = len([item for item in results if item.status == "error"])
        passed = len([item for item in results if item.status == "passed"])

        proposal_tp = proposal_fp = proposal_fn = proposal_tn = 0
        text_tp = text_fp = text_fn = 0
        duplicate_tp = duplicate_fp = duplicate_fn = duplicate_tn = 0
        ignored_total = false_creations = 0
        expected_proposals = missed_proposals = 0
        action_hits = 0

        for item in results:
            expected = item.expected
            actual = item.actual
            expected_is_proposal = bool(expected.get("is_proposal"))
            actual_is_proposal = bool(actual.get("is_proposal"))
            expected_duplicate = bool(expected.get("duplicate"))
            actual_duplicate = bool(actual.get("duplicate"))
            text_match = bool(item.metrics.get("proposal_text_match"))

            if expected_is_proposal:
                expected_proposals += 1
                if actual_is_proposal:
                    proposal_tp += 1
                else:
                    proposal_fn += 1
                    missed_proposals += 1
            elif actual_is_proposal:
                proposal_fp += 1
            else:
                proposal_tn += 1

            if expected_is_proposal and actual_is_proposal and text_match:
                text_tp += 1
            else:
                if actual_is_proposal:
                    text_fp += 1
                if expected_is_proposal:
                    text_fn += 1

            if expected_duplicate and actual_duplicate:
                duplicate_tp += 1
            elif not expected_duplicate and actual_duplicate:
                duplicate_fp += 1
            elif expected_duplicate and not actual_duplicate:
                duplicate_fn += 1
            else:
                duplicate_tn += 1

            if expected.get("action") == "ignore":
                ignored_total += 1
                if actual.get("action") != "ignore":
                    false_creations += 1
            if item.metrics.get("action_match"):
                action_hits += 1

        proposal_scores = AdminChangeProposalEvalService._prf(
            proposal_tp,
            proposal_fp,
            proposal_fn,
        )
        text_scores = AdminChangeProposalEvalService._prf(text_tp, text_fp, text_fn)
        duplicate_scores = AdminChangeProposalEvalService._prf(
            duplicate_tp,
            duplicate_fp,
            duplicate_fn,
        )
        return {
            "cases_total": total,
            "passed": passed,
            "failed": len([item for item in results if item.status == "failed"]),
            "errors": errors,
            "pass_rate": round(passed / total, 4) if total else 0,
            "proposal_tp": proposal_tp,
            "proposal_fp": proposal_fp,
            "proposal_fn": proposal_fn,
            "proposal_tn": proposal_tn,
            "proposal_precision": proposal_scores["precision"],
            "proposal_recall": proposal_scores["recall"],
            "proposal_f1": proposal_scores["f1"],
            "proposal_text_tp": text_tp,
            "proposal_text_fp": text_fp,
            "proposal_text_fn": text_fn,
            "proposal_text_precision": text_scores["precision"],
            "proposal_text_recall": text_scores["recall"],
            "proposal_text_f1": text_scores["f1"],
            "semantic_match_rate": round(text_tp / max(expected_proposals, 1), 4),
            "duplicate_tp": duplicate_tp,
            "duplicate_fp": duplicate_fp,
            "duplicate_fn": duplicate_fn,
            "duplicate_tn": duplicate_tn,
            "duplicate_precision": duplicate_scores["precision"],
            "duplicate_recall": duplicate_scores["recall"],
            "duplicate_f1": duplicate_scores["f1"],
            "false_creation_rate": round(false_creations / max(ignored_total, 1), 4),
            "missed_proposal_rate": round(missed_proposals / max(expected_proposals, 1), 4),
            "structured_artifact_rate": round(text_tp / max(expected_proposals, 1), 4),
            "action_accuracy": round(action_hits / max(total, 1), 4),
        }

    @staticmethod
    async def _route_case(
        *,
        case: ChangeProposalEvalCasePayload,
        project_id: str | None,
        actor: User,
        db: AsyncSession,
    ) -> tuple[dict[str, Any], str | None]:
        state = await run_chat_routing_eval_graph(
            db=db,
            task_id=case.task_id,
            project_id=project_id,
            actor_user_id=actor.id,
            task_title=case.task_title,
            task_status=case.task_status,
            task_content=case.task_content,
            message_content=case.message_content,
            validation_result=None,
            requested_agent=case.requested_agent,
        )
        return dict(state.get("actual_route") or {}), (
            str(state.get("graph_run_id")) if state.get("graph_run_id") else None
        )

    @staticmethod
    async def _extract_case(
        *,
        case: ChangeProposalEvalCasePayload,
        project_id: str | None,
        actor: User,
        db: AsyncSession,
    ) -> tuple[dict[str, Any], str | None]:
        state = await run_change_tracker_agent_graph(
            db=db,
            actor_user_id=actor.id,
            task_id=case.task_id,
            project_id=project_id,
            task_title=case.task_title,
            task_status=case.task_status,
            task_content=case.task_content,
            message_content=case.message_content,
            routing_mode="change_proposal_eval",
        )
        return dict(state), (
            str(state.get("graph_run_id")) if state.get("graph_run_id") else None
        )

    @staticmethod
    async def _run_case(
        *,
        case: ChangeProposalEvalCasePayload,
        payload: ChangeProposalEvalRunPayload,
        actor: User,
        db: AsyncSession,
    ) -> ChangeProposalEvalCaseResultRead:
        started = perf_counter()
        project_id = case.project_id or payload.project_id
        actual_route: dict[str, Any] | None = None
        route_graph_run_id: str | None = None
        change_graph_run_id: str | None = None
        try:
            should_extract = payload.config.mode == "extract_all"
            if payload.config.mode == "route_then_extract":
                actual_route, route_graph_run_id = await AdminChangeProposalEvalService._route_case(
                    case=case,
                    project_id=project_id,
                    actor=actor,
                    db=db,
                )
                should_extract = (
                    actual_route.get("target_agent_key") == "change-tracker"
                    or actual_route.get("message_type") == "change_proposal"
                )

            change_state: dict[str, Any] = {}
            if should_extract:
                change_state, change_graph_run_id = (
                    await AdminChangeProposalEvalService._extract_case(
                        case=case,
                        project_id=project_id,
                        actor=actor,
                        db=db,
                    )
                )

            source_ref = dict(change_state.get("source_ref") or {})
            actual_is_proposal = bool(should_extract)
            actual_duplicate = bool(source_ref.get("duplicate_proposal"))
            actual_proposal_text = (
                str(change_state.get("proposal_text"))
                if change_state.get("proposal_text") is not None
                else None
            )
            actual_action = AdminChangeProposalEvalService._actual_action(
                actual_is_proposal=actual_is_proposal,
                actual_duplicate=actual_duplicate,
            )
            metrics = AdminChangeProposalEvalService._case_metrics(
                case=case,
                actual_is_proposal=actual_is_proposal,
                actual_proposal_text=actual_proposal_text,
                actual_duplicate=actual_duplicate,
                actual_action=actual_action,
                threshold=payload.config.semantic_match_threshold,
            )
            return ChangeProposalEvalCaseResultRead(
                case_external_id=case.external_id,
                status="passed" if metrics["passed"] else "failed",
                expected=AdminChangeProposalEvalService._expected(case),
                actual={
                    "is_proposal": actual_is_proposal,
                    "proposal_text": actual_proposal_text,
                    "duplicate": actual_duplicate,
                    "action": actual_action,
                    "route": actual_route,
                    "source_ref": source_ref,
                },
                metrics=metrics,
                route_graph_run_id=route_graph_run_id,
                change_graph_run_id=change_graph_run_id,
                latency_ms=int((perf_counter() - started) * 1000),
            )
        except Exception as exc:  # noqa: BLE001
            return ChangeProposalEvalCaseResultRead(
                case_external_id=case.external_id,
                status="error",
                expected=AdminChangeProposalEvalService._expected(case),
                actual={"route": actual_route},
                metrics={"passed": False, "error": True},
                route_graph_run_id=route_graph_run_id,
                change_graph_run_id=change_graph_run_id,
                latency_ms=int((perf_counter() - started) * 1000),
                error_message=str(exc)[:1000],
            )

    @staticmethod
    async def run(
        payload: ChangeProposalEvalRunPayload,
        actor: User,
        db: AsyncSession,
    ) -> ChangeProposalEvalRunRead:
        started_at = datetime.now(UTC)
        started = perf_counter()
        case_results = [
            await AdminChangeProposalEvalService._run_case(
                case=case,
                payload=payload,
                actor=actor,
                db=db,
            )
            for case in payload.cases
        ]
        summary = AdminChangeProposalEvalService._summarize(case_results)
        errors = int(summary.get("errors") or 0)
        if errors == len(case_results):
            run_status: ChangeProposalEvalRunStatus = "error"
        elif errors:
            run_status = "partial_error"
        else:
            run_status = "success"
        finished_at = datetime.now(UTC)
        return ChangeProposalEvalRunRead(
            status=run_status,
            config=payload.config,
            summary_metrics=summary,
            case_results=case_results,
            started_at=started_at,
            finished_at=finished_at,
            latency_ms=int((perf_counter() - started) * 1000),
        )
