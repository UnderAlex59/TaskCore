from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from io import StringIO
from time import perf_counter
from typing import Any, cast

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.qure_eval_weak_word_judge_graph import run_qure_eval_weak_word_judge_graph
from app.agents.validation_graph import run_validation_eval_graph
from app.core.database import AsyncSessionLocal
from app.models.llm_request_log import LLMRequestLog
from app.models.project import Project
from app.models.qure_eval import QureEvalCaseResult, QureEvalRun
from app.models.user import User
from app.schemas.admin_qure_eval import (
    QureEvalCaseResultRead,
    QureEvalRunCreateRead,
    QureEvalRunListItemRead,
    QureEvalRunPageRead,
    QureEvalRunRead,
    QureEvalRunStatus,
)
from app.services.audit_service import AuditService

QURE_REQUIRED_COLUMNS = ("id", "requirement", "defect", "weak_word")
QURE_SELECTION_STRATEGY = "stratified_by_defect_then_weak_word_v1"
QURE_CORE_ONLY_SETTINGS = {
    "core_rules": True,
    "custom_rules": False,
    "context_questions": False,
}


@dataclass(frozen=True, slots=True)
class QureCsvRow:
    row_index: int
    source_id: str
    requirement: str
    defect: str
    weak_word: str

    @property
    def expected_verdict(self) -> str:
        return "needs_rework" if self.defect == "defect" else "approved"


class AdminQureEvalService:
    @staticmethod
    def parse_qure_csv(content: bytes) -> list[QureCsvRow]:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="QuRE CSV должен быть в UTF-8.",
            ) from exc
        reader = csv.DictReader(StringIO(text))
        fieldnames = [name.strip() for name in (reader.fieldnames or [])]
        if tuple(fieldnames) != QURE_REQUIRED_COLUMNS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "QuRE CSV должен содержать ровно колонки "
                    "id, requirement, defect, weak_word."
                ),
            )
        reader.fieldnames = fieldnames

        rows: list[QureCsvRow] = []
        seen_ids: set[str] = set()
        for row_index, row in enumerate(reader):
            source_id = str(row.get("id") or "").strip()
            requirement = str(row.get("requirement") or "").strip()
            defect = str(row.get("defect") or "").strip().casefold()
            weak_word = str(row.get("weak_word") or "").strip()
            if not source_id or not requirement or not defect or not weak_word:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "QuRE CSV содержит пустое обязательное значение "
                        f"в строке {row_index + 2}."
                    ),
                )
            if source_id in seen_ids:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"QuRE CSV содержит повторяющийся id: {source_id}.",
                )
            if defect not in {"ok", "defect"}:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        f"QuRE CSV содержит неизвестный defect '{defect}' "
                        f"в строке {row_index + 2}."
                    ),
                )
            seen_ids.add(source_id)
            rows.append(
                QureCsvRow(
                    row_index=row_index,
                    source_id=source_id,
                    requirement=requirement,
                    defect=defect,
                    weak_word=weak_word,
                )
            )

        if not rows:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="QuRE CSV не содержит строк данных.",
            )
        return rows

    @staticmethod
    def _largest_remainder_quotas(counts: dict[str, int], limit: int) -> dict[str, int]:
        total = sum(counts.values())
        if limit >= total:
            return dict(counts)
        if total <= 0 or limit <= 0:
            return {key: 0 for key in counts}

        quotas: dict[str, int] = {}
        remainders: dict[str, float] = {}
        for key, count in counts.items():
            exact = count * limit / total
            quota = min(count, int(exact))
            quotas[key] = quota
            remainders[key] = exact - quota

        remaining = limit - sum(quotas.values())
        while remaining > 0:
            eligible = [key for key, count in counts.items() if quotas[key] < count]
            if not eligible:
                break
            eligible.sort(key=lambda key: (-remainders[key], -counts[key], str(key)))
            quotas[eligible[0]] += 1
            remaining -= 1
        return quotas

    @staticmethod
    def _even_sample(rows: list[QureCsvRow], quota: int) -> list[QureCsvRow]:
        if quota <= 0:
            return []
        if quota >= len(rows):
            return list(rows)
        if quota == 1:
            return [rows[len(rows) // 2]]
        indexes = [
            round(index * (len(rows) - 1) / (quota - 1))
            for index in range(quota)
        ]
        deduped: list[int] = []
        for index in indexes:
            if index not in deduped:
                deduped.append(index)
        cursor = 0
        while len(deduped) < quota and cursor < len(rows):
            if cursor not in deduped:
                deduped.append(cursor)
            cursor += 1
        deduped.sort()
        return [rows[index] for index in deduped[:quota]]

    @staticmethod
    def select_stratified_rows(rows: list[QureCsvRow], row_limit: int) -> list[QureCsvRow]:
        if row_limit < 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="row_limit должен быть больше 0.",
            )
        if row_limit >= len(rows):
            return list(rows)

        by_defect: dict[str, list[QureCsvRow]] = {}
        for row in rows:
            by_defect.setdefault(row.defect, []).append(row)
        defect_quotas = AdminQureEvalService._largest_remainder_quotas(
            {key: len(value) for key, value in by_defect.items()},
            row_limit,
        )

        selected: list[QureCsvRow] = []
        for defect, defect_quota in sorted(defect_quotas.items()):
            if defect_quota <= 0:
                continue
            by_weak_word: dict[str, list[QureCsvRow]] = {}
            for row in by_defect[defect]:
                by_weak_word.setdefault(row.weak_word.casefold(), []).append(row)
            weak_word_quotas = AdminQureEvalService._largest_remainder_quotas(
                {key: len(value) for key, value in by_weak_word.items()},
                defect_quota,
            )
            for weak_word, weak_word_quota in sorted(weak_word_quotas.items()):
                selected.extend(
                    AdminQureEvalService._even_sample(
                        by_weak_word[weak_word],
                        weak_word_quota,
                    )
                )
        return sorted(selected, key=lambda row: row.row_index)

    @staticmethod
    def _expected_verdict(defect: str) -> str:
        return "needs_rework" if defect == "defect" else "approved"

    @staticmethod
    def _prf(tp: int, fp: int, fn: int) -> dict[str, float]:
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }

    @staticmethod
    def _bool_or_none(value: object) -> bool | None:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().casefold()
            if normalized in {"true", "yes", "1"}:
                return True
            if normalized in {"false", "no", "0"}:
                return False
        return None

    @staticmethod
    def _case_metrics(
        *,
        defect: str,
        expected_verdict: str,
        actual_verdict: str,
        judge_match: bool,
    ) -> dict[str, Any]:
        expected_positive = defect == "defect"
        actual_positive = actual_verdict == "needs_rework"
        return {
            "expected_positive": expected_positive,
            "actual_positive": actual_positive,
            "verdict_match": expected_verdict == actual_verdict,
            "verdict_tp": int(expected_positive and actual_positive),
            "verdict_fp": int(not expected_positive and actual_positive),
            "verdict_tn": int(not expected_positive and not actual_positive),
            "verdict_fn": int(expected_positive and not actual_positive),
            "weak_word_match": judge_match,
            "weak_word_tp": int(expected_positive and judge_match),
            "weak_word_fp": int(not expected_positive and judge_match),
            "weak_word_fn": int(expected_positive and not judge_match),
        }

    @staticmethod
    async def _project_name(db: AsyncSession, project_id: str) -> str | None:
        project = await db.get(Project, project_id)
        return project.name if project is not None else None

    @staticmethod
    async def _run_read_item(run: QureEvalRun, db: AsyncSession) -> QureEvalRunListItemRead:
        return QureEvalRunListItemRead(
            id=run.id,
            project_id=run.project_id,
            project_name=await AdminQureEvalService._project_name(db, run.project_id),
            filename=run.filename,
            file_sha256=run.file_sha256,
            row_limit=run.row_limit,
            selection_strategy=run.selection_strategy,
            total_rows=run.total_rows,
            selected_rows=run.selected_rows,
            status=cast(QureEvalRunStatus, run.status),
            summary_metrics=run.summary_metrics,
            started_at=run.started_at,
            finished_at=run.finished_at,
            latency_ms=run.latency_ms,
            error_message=run.error_message,
            created_at=run.created_at,
        )

    @staticmethod
    def _case_result_read(result: QureEvalCaseResult) -> QureEvalCaseResultRead:
        return QureEvalCaseResultRead(
            id=result.id,
            run_id=result.run_id,
            graph_run_id=result.graph_run_id,
            judge_graph_run_id=result.judge_graph_run_id,
            row_index=result.row_index,
            source_id=result.source_id,
            requirement=result.requirement,
            defect=cast(Any, result.defect),
            weak_word=result.weak_word,
            expected_verdict=cast(Any, result.expected_verdict),
            actual_result=dict(result.actual_result or {}),
            judge_payload=dict(result.judge_payload) if result.judge_payload else None,
            metrics=dict(result.metrics or {}),
            status=cast(Any, result.status),
            latency_ms=result.latency_ms,
            error_message=result.error_message,
            created_at=result.created_at,
        )

    @staticmethod
    async def create_run(
        *,
        filename: str,
        content: bytes,
        project_id: str,
        row_limit: int,
        actor: User,
        db: AsyncSession,
    ) -> QureEvalRunCreateRead:
        project = await db.get(Project, project_id)
        if project is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Проект для QuRE Eval не найден.",
            )
        rows = AdminQureEvalService.parse_qure_csv(content)
        selected_rows = AdminQureEvalService.select_stratified_rows(rows, row_limit)
        run = QureEvalRun(
            project_id=project.id,
            created_by=actor.id,
            filename=filename[:255] or "QuRE.csv",
            file_sha256=hashlib.sha256(content).hexdigest(),
            row_limit=row_limit,
            selection_strategy=QURE_SELECTION_STRATEGY,
            total_rows=len(rows),
            selected_rows=len(selected_rows),
            status="queued",
        )
        db.add(run)
        await db.flush()
        for row in selected_rows:
            db.add(
                QureEvalCaseResult(
                    run_id=run.id,
                    row_index=row.row_index,
                    source_id=row.source_id,
                    requirement=row.requirement,
                    defect=row.defect,
                    weak_word=row.weak_word,
                    expected_verdict=row.expected_verdict,
                    actual_result={},
                    judge_payload=None,
                    metrics={},
                    status="queued",
                )
            )
        AuditService.record(
            db,
            actor_user_id=actor.id,
            event_type="admin.qure_eval_run_created",
            entity_type="qure_eval_run",
            entity_id=run.id,
            project_id=project.id,
            metadata={"selected_rows": len(selected_rows), "row_limit": row_limit},
        )
        await db.commit()
        await db.refresh(run)
        return QureEvalRunCreateRead(
            id=run.id,
            project_id=run.project_id,
            status=cast(QureEvalRunStatus, run.status),
            row_limit=run.row_limit,
            total_rows=run.total_rows,
            selected_rows=run.selected_rows,
            selection_strategy=run.selection_strategy,
            created_at=run.created_at,
        )

    @staticmethod
    async def process_run(run_id: str) -> None:
        async with AsyncSessionLocal() as db:
            run = await db.get(QureEvalRun, run_id)
            if run is None:
                return
            run.status = "running"
            run.started_at = datetime.now(UTC)
            await db.commit()
            started = perf_counter()
            try:
                await AdminQureEvalService._process_run_inner(run.id, db)
                run = await db.get(QureEvalRun, run_id)
                if run is not None:
                    run.status = "success"
                    run.finished_at = datetime.now(UTC)
                    run.latency_ms = int((perf_counter() - started) * 1000)
                    run.summary_metrics = await AdminQureEvalService._summarize_run(run, db)
                    await db.commit()
            except Exception as exc:  # noqa: BLE001
                run = await db.get(QureEvalRun, run_id)
                if run is not None:
                    run.status = "error"
                    run.finished_at = datetime.now(UTC)
                    run.latency_ms = int((perf_counter() - started) * 1000)
                    run.error_message = str(exc)[:1000]
                    await db.commit()

    @staticmethod
    async def _process_run_inner(run_id: str, db: AsyncSession) -> None:
        run = await db.get(QureEvalRun, run_id)
        if run is None:
            return
        results = list(
            (
                await db.execute(
                    select(QureEvalCaseResult)
                    .where(QureEvalCaseResult.run_id == run.id)
                    .order_by(QureEvalCaseResult.row_index.asc())
                )
            )
            .scalars()
            .all()
        )
        for result in results:
            await AdminQureEvalService._run_case(run, result, db)

    @staticmethod
    async def _run_case(run: QureEvalRun, result: QureEvalCaseResult, db: AsyncSession) -> None:
        started = perf_counter()
        error_message: str | None = None
        actual: dict[str, Any] = {}
        judge_payload: dict[str, Any] | None = None
        graph_run_id: str | None = None
        judge_graph_run_id: str | None = None
        metrics: dict[str, Any] = {}
        status_value = "error"
        try:
            validation_state = await run_validation_eval_graph(
                db=db,
                actor_user_id=run.created_by,
                project_id=run.project_id,
                title=f"QuRE {result.source_id}: {result.weak_word}",
                content=result.requirement,
                tags=["qure", "weak-word", result.weak_word],
                custom_rules=[],
                related_tasks=[],
                attachment_names=[],
                historical_questions=[],
                validation_node_settings=QURE_CORE_ONLY_SETTINGS,
                provider_config_id=None,
                prompt_overrides=None,
            )
            graph_run_id = (
                str(validation_state.get("graph_run_id"))
                if validation_state.get("graph_run_id")
                else None
            )
            actual = {
                "verdict": str(validation_state.get("verdict", "approved")),
                "issues": list(validation_state.get("issues", [])),
                "questions": list(validation_state.get("questions", [])),
                "llm_diagnostics": list(validation_state.get("llm_diagnostics", [])),
                "core_issues": list(validation_state.get("core_issues", [])),
                "core_questions": list(validation_state.get("core_questions", [])),
            }
            actual_issues = [dict(item) for item in actual.get("issues", [])]
            judge_state = await run_qure_eval_weak_word_judge_graph(
                db=db,
                actor_user_id=run.created_by,
                project_id=run.project_id,
                requirement=result.requirement,
                weak_word=result.weak_word,
                qure_defect=result.defect,
                expected_verdict=result.expected_verdict,
                actual_verdict=str(actual.get("verdict", "approved")),
                actual_issues=actual_issues,
            )
            judge_payload = dict(judge_state.get("judge_payload", {}))
            judge_graph_run_id = (
                str(judge_state.get("judge_graph_run_id"))
                if judge_state.get("judge_graph_run_id")
                else None
            )

            judge_ok = bool(judge_payload.get("ok") if judge_payload else False)
            judge_passed = (
                AdminQureEvalService._bool_or_none(judge_payload.get("passed"))
                if judge_payload
                else None
            )
            if judge_passed is None and judge_payload:
                judge_passed = AdminQureEvalService._bool_or_none(judge_payload.get("match"))
            weak_word_match = (
                AdminQureEvalService._bool_or_none(judge_payload.get("weak_word_match"))
                if judge_payload
                else None
            )
            if weak_word_match is None and judge_payload:
                weak_word_match = AdminQureEvalService._bool_or_none(judge_payload.get("match"))

            metrics = AdminQureEvalService._case_metrics(
                defect=result.defect,
                expected_verdict=result.expected_verdict,
                actual_verdict=str(actual.get("verdict", "approved")),
                judge_match=bool(weak_word_match),
            )
            metrics["judge_ok"] = judge_ok
            metrics["judge_score"] = judge_payload.get("score") if judge_payload else 0.0
            metrics["judge_passed"] = judge_passed if judge_passed is not None else False
            metrics["result_source"] = "llm_judge"
            if not judge_ok or judge_passed is None:
                status_value = "error"
                error_message = str(
                    (judge_payload or {}).get("rationale")
                    or "QuRE Eval judge did not return a valid decision."
                )[:1000]
            else:
                status_value = "passed" if judge_passed else "failed"
        except Exception as exc:  # noqa: BLE001
            error_message = str(exc)[:1000]
            metrics = {"error": True, "result_source": "llm_judge"}

        result.graph_run_id = graph_run_id
        result.judge_graph_run_id = judge_graph_run_id
        result.actual_result = actual
        result.judge_payload = judge_payload
        result.metrics = metrics
        result.status = status_value
        result.latency_ms = int((perf_counter() - started) * 1000)
        result.error_message = error_message
        await db.commit()

    @staticmethod
    async def _token_totals(
        graph_run_ids: list[str],
        db: AsyncSession,
    ) -> dict[str, dict[str, Any]]:
        if not graph_run_ids:
            return {}
        logs = list(
            (
                await db.execute(
                    select(LLMRequestLog).where(LLMRequestLog.graph_run_id.in_(graph_run_ids))
                )
            )
            .scalars()
            .all()
        )
        totals: dict[str, dict[str, Any]] = {}
        for log in logs:
            if not log.graph_run_id:
                continue
            item = totals.setdefault(
                log.graph_run_id,
                {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "estimated_cost_usd": Decimal("0"),
                },
            )
            item["prompt_tokens"] += int(log.prompt_tokens or 0)
            item["completion_tokens"] += int(log.completion_tokens or 0)
            item["total_tokens"] += int(log.total_tokens or 0)
            if log.estimated_cost_usd is not None:
                item["estimated_cost_usd"] += Decimal(log.estimated_cost_usd)
        return totals

    @staticmethod
    async def _summarize_run(run: QureEvalRun, db: AsyncSession) -> dict[str, Any]:
        results = list(
            (
                await db.execute(
                    select(QureEvalCaseResult).where(QureEvalCaseResult.run_id == run.id)
                )
            )
            .scalars()
            .all()
        )
        graph_run_ids: list[str] = []
        for result in results:
            graph_run_ids.extend(
                value for value in (result.graph_run_id, result.judge_graph_run_id) if value
            )
        token_totals = await AdminQureEvalService._token_totals(
            list(dict.fromkeys(graph_run_ids)),
            db,
        )
        token_summary = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "estimated_cost_usd": Decimal("0"),
        }
        for graph_run_id in graph_run_ids:
            if graph_run_id not in token_totals:
                continue
            graph_tokens = token_totals[graph_run_id]
            token_summary["prompt_tokens"] += int(graph_tokens["prompt_tokens"])
            token_summary["completion_tokens"] += int(graph_tokens["completion_tokens"])
            token_summary["total_tokens"] += int(graph_tokens["total_tokens"])
            token_summary["estimated_cost_usd"] += Decimal(graph_tokens["estimated_cost_usd"])

        verdict_tp = sum(int(item.metrics.get("verdict_tp") or 0) for item in results)
        verdict_fp = sum(int(item.metrics.get("verdict_fp") or 0) for item in results)
        verdict_tn = sum(int(item.metrics.get("verdict_tn") or 0) for item in results)
        verdict_fn = sum(int(item.metrics.get("verdict_fn") or 0) for item in results)
        weak_word_tp = sum(int(item.metrics.get("weak_word_tp") or 0) for item in results)
        weak_word_fp = sum(int(item.metrics.get("weak_word_fp") or 0) for item in results)
        weak_word_fn = sum(int(item.metrics.get("weak_word_fn") or 0) for item in results)
        verdict_scores = AdminQureEvalService._prf(verdict_tp, verdict_fp, verdict_fn)
        weak_word_scores = AdminQureEvalService._prf(weak_word_tp, weak_word_fp, weak_word_fn)
        confusion = {
            "defect": {
                "needs_rework": verdict_tp,
                "approved": verdict_fn,
            },
            "ok": {
                "needs_rework": verdict_fp,
                "approved": verdict_tn,
            },
        }
        by_weak_word: dict[str, dict[str, Any]] = {}
        for item in results:
            bucket = by_weak_word.setdefault(
                item.weak_word,
                {
                    "total": 0,
                    "defect": 0,
                    "ok": 0,
                    "verdict_tp": 0,
                    "verdict_fp": 0,
                    "verdict_fn": 0,
                    "weak_word_tp": 0,
                    "weak_word_fp": 0,
                    "weak_word_fn": 0,
                },
            )
            bucket["total"] += 1
            bucket[item.defect] += 1
            for key in (
                "verdict_tp",
                "verdict_fp",
                "verdict_fn",
                "weak_word_tp",
                "weak_word_fp",
                "weak_word_fn",
            ):
                bucket[key] += int(item.metrics.get(key) or 0)
        for bucket in by_weak_word.values():
            bucket["verdict"] = AdminQureEvalService._prf(
                int(bucket["verdict_tp"]),
                int(bucket["verdict_fp"]),
                int(bucket["verdict_fn"]),
            )
            bucket["weak_word"] = AdminQureEvalService._prf(
                int(bucket["weak_word_tp"]),
                int(bucket["weak_word_fp"]),
                int(bucket["weak_word_fn"]),
            )

        total = len(results)
        judge_passed = sum(1 for item in results if item.status == "passed")
        judge_failed = sum(1 for item in results if item.status == "failed")
        judge_errors = sum(
            1
            for item in results
            if item.status == "error"
            and (
                not item.judge_payload
                or not bool(item.judge_payload.get("ok"))
            )
        )
        return {
            "cases_total": total,
            "passed": judge_passed,
            "failed": judge_failed,
            "errors": sum(1 for item in results if item.status == "error"),
            "validator_errors": sum(
                1
                for item in results
                if item.status == "error" and not item.judge_payload
            ),
            "judge_errors": judge_errors,
            "judge_passed": judge_passed,
            "judge_failed": judge_failed,
            "judge_pass_rate": round(judge_passed / total, 4) if total else 0,
            "verdict_confusion_matrix": confusion,
            "verdict_accuracy": round((verdict_tp + verdict_tn) / total, 4) if total else 0,
            "verdict_precision": verdict_scores["precision"],
            "verdict_recall": verdict_scores["recall"],
            "verdict_f1": verdict_scores["f1"],
            "weak_word_precision": weak_word_scores["precision"],
            "weak_word_recall": weak_word_scores["recall"],
            "weak_word_f1": weak_word_scores["f1"],
            "weak_word_breakdown": by_weak_word,
            "token_totals": {
                "prompt_tokens": int(token_summary["prompt_tokens"]),
                "completion_tokens": int(token_summary["completion_tokens"]),
                "total_tokens": int(token_summary["total_tokens"]),
                "estimated_cost_usd": float(token_summary["estimated_cost_usd"]),
            },
        }

    @staticmethod
    async def list_runs(
        db: AsyncSession,
        *,
        run_status: QureEvalRunStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> QureEvalRunPageRead:
        conditions = []
        if run_status:
            conditions.append(QureEvalRun.status == run_status)
        total = (
            await db.execute(select(func.count()).select_from(QureEvalRun).where(*conditions))
        ).scalar_one()
        runs = list(
            (
                await db.execute(
                    select(QureEvalRun)
                    .where(*conditions)
                    .order_by(QureEvalRun.created_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            .scalars()
            .all()
        )
        return QureEvalRunPageRead(
            page=page,
            page_size=page_size,
            total=int(total),
            items=[await AdminQureEvalService._run_read_item(run, db) for run in runs],
        )

    @staticmethod
    async def get_run(run_id: str, db: AsyncSession) -> QureEvalRunRead:
        run = await db.get(QureEvalRun, run_id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="QuRE Eval-запуск не найден.",
            )
        results = list(
            (
                await db.execute(
                    select(QureEvalCaseResult)
                    .where(QureEvalCaseResult.run_id == run.id)
                    .order_by(QureEvalCaseResult.row_index.asc())
                )
            )
            .scalars()
            .all()
        )
        base = await AdminQureEvalService._run_read_item(run, db)
        return QureEvalRunRead(
            **base.model_dump(),
            case_results=[AdminQureEvalService._case_result_read(result) for result in results],
        )

    @staticmethod
    def _json_dumps(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, default=str)

    @staticmethod
    def _export_csv(run: QureEvalRunRead) -> str:
        output = StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "row_index",
                "id",
                "requirement",
                "defect",
                "weak_word",
                "expected_verdict",
                "actual_verdict",
                "status",
                "judge_passed",
                "judge_match",
                "judge_score",
                "actual_result_json",
                "judge_payload_json",
                "metrics_json",
                "error_message",
            ],
        )
        writer.writeheader()
        for item in run.case_results:
            writer.writerow(
                {
                    "row_index": item.row_index,
                    "id": item.source_id,
                    "requirement": item.requirement,
                    "defect": item.defect,
                    "weak_word": item.weak_word,
                    "expected_verdict": item.expected_verdict,
                    "actual_verdict": item.actual_result.get("verdict"),
                    "status": item.status,
                    "judge_passed": (item.judge_payload or {}).get("passed"),
                    "judge_match": (item.judge_payload or {}).get("match"),
                    "judge_score": (item.judge_payload or {}).get("score"),
                    "actual_result_json": AdminQureEvalService._json_dumps(item.actual_result),
                    "judge_payload_json": AdminQureEvalService._json_dumps(
                        item.judge_payload or {}
                    ),
                    "metrics_json": AdminQureEvalService._json_dumps(item.metrics),
                    "error_message": item.error_message or "",
                }
            )
        return output.getvalue()

    @staticmethod
    async def export_run(
        run_id: str,
        export_format: str,
        db: AsyncSession,
    ) -> tuple[str, str, str]:
        run = await AdminQureEvalService.get_run(run_id, db)
        if export_format == "json":
            return (
                f"qure-eval-{run.id}.json",
                "application/json; charset=utf-8",
                AdminQureEvalService._json_dumps(run.model_dump(mode="json")),
            )
        if export_format == "csv":
            return (
                f"qure-eval-{run.id}.csv",
                "text/csv; charset=utf-8",
                AdminQureEvalService._export_csv(run),
            )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Поддерживаются только json и csv.",
        )

    @staticmethod
    async def delete_run(run_id: str, actor: User, db: AsyncSession) -> None:
        run = await db.get(QureEvalRun, run_id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="QuRE Eval-запуск не найден.",
            )
        if run.status in {"queued", "running"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Нельзя удалить активный QuRE Eval-запуск.",
            )
        AuditService.record(
            db,
            actor_user_id=actor.id,
            event_type="admin.qure_eval_run_deleted",
            entity_type="qure_eval_run",
            entity_id=run.id,
            project_id=run.project_id,
        )
        await db.delete(run)
        await db.commit()


def normalize_weak_word_for_tests(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())
