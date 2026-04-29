from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status
from qdrant_client import models
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.change_proposal import ChangeProposal
from app.models.task import Task, TaskAttachment
from app.models.user import User
from app.models.validation_question import ValidationQuestion
from app.schemas.admin_qdrant import (
    QdrantCollectionDiagnosticRead,
    QdrantCoverageTaskRead,
    QdrantDuplicateProposalProbePayload,
    QdrantOverviewRead,
    QdrantProjectCoverageRead,
    QdrantProjectCoverageSummaryRead,
    QdrantProjectQuestionsProbePayload,
    QdrantRelatedTasksProbePayload,
    QdrantScenarioHeuristicRead,
    QdrantScenarioProbeRead,
    QdrantScenarioResultRead,
    QdrantTaskResyncRead,
)
from app.services.attachment_content_service import AttachmentContentService
from app.services.audit_service import AuditService
from app.services.project_service import ProjectService
from app.services.qdrant_service import (
    PROJECT_QUESTIONS_COLLECTION,
    TASK_KNOWLEDGE_COLLECTION,
    QdrantService,
)
from app.services.rag_service import RagService
from app.services.task_service import TaskService
from app.services.validation_question_service import ValidationQuestionService

_DUPLICATE_PROPOSAL_NEAR_THRESHOLD_DELTA = 0.05


class AdminQdrantService:
    @staticmethod
    def _optional_int_attr(
        collection_info: models.CollectionInfo,
        attribute_name: str,
    ) -> int | None:
        value = getattr(collection_info, attribute_name, None)
        return int(value) if value is not None else None

    @staticmethod
    def _match_value_condition(key: str, value: str) -> models.FieldCondition:
        return models.FieldCondition(
            key=key,
            match=models.MatchValue(value=value),
        )

    @staticmethod
    def _task_filter(task_id: str) -> models.Filter:
        return models.Filter(
            must=[AdminQdrantService._match_value_condition("metadata.task_id", task_id)]
        )

    @staticmethod
    def _extract_distance(collection_info: models.CollectionInfo) -> str | None:
        vectors = collection_info.config.params.vectors
        if isinstance(vectors, models.VectorParams):
            return vectors.distance.value
        if isinstance(vectors, dict):
            for vector_params in vectors.values():
                if isinstance(vector_params, models.VectorParams):
                    return vector_params.distance.value
        return None

    @staticmethod
    def _collection_checks(
        collection_info: models.CollectionInfo,
    ) -> tuple[bool | None, bool | None, bool | None, bool | None]:
        metadata = collection_info.config.metadata or {}
        embedding_config = QdrantService.get_embedding_configuration()
        expected_provider = embedding_config["provider"]
        expected_model = embedding_config["model"]
        expected_vector_size = embedding_config["vector_size"]
        actual_vector_size = QdrantService._extract_vector_size(collection_info)

        provider_matches = (
            metadata.get("embedding_provider") == expected_provider
            if expected_provider is not None
            else None
        )
        model_matches = (
            metadata.get("embedding_model") == expected_model
            if expected_model is not None
            else None
        )
        vector_size_matches = (
            actual_vector_size == expected_vector_size
            if expected_vector_size is not None
            else None
        )
        comparable_checks = [
            check
            for check in (provider_matches, model_matches, vector_size_matches)
            if check is not None
        ]
        metadata_matches = all(comparable_checks) if comparable_checks else None
        return provider_matches, model_matches, vector_size_matches, metadata_matches

    @staticmethod
    def _collection_warnings(
        collection_name: str,
        *,
        exists: bool,
        points_count: int | None,
        provider_matches: bool | None,
        model_matches: bool | None,
        vector_size_matches: bool | None,
    ) -> list[str]:
        warnings: list[str] = []
        if not exists:
            warnings.append(f"Коллекция {collection_name} пока не создана.")
            return warnings
        if points_count == 0:
            warnings.append("Коллекция существует, но пока не содержит точек.")
        if provider_matches is False:
            warnings.append(
                "Провайдер эмбеддингов в metadata коллекции "
                "не совпадает с текущей конфигурацией."
            )
        if model_matches is False:
            warnings.append(
                "Модель эмбеддингов в metadata коллекции "
                "не совпадает с текущей конфигурацией."
            )
        if vector_size_matches is False:
            warnings.append(
                "Размер вектора коллекции не совпадает с ожидаемым размером "
                "текущих эмбеддингов."
            )
        return warnings

    @staticmethod
    async def get_overview() -> QdrantOverviewRead:
        embedding_config = QdrantService.get_embedding_configuration()
        generated_at = datetime.now(UTC)
        connection_error: str | None = None
        connected = True
        collections: list[QdrantCollectionDiagnosticRead] = []

        try:
            client = QdrantService._get_client()
            client.get_collections()
        except Exception as exc:
            connected = False
            connection_error = str(exc)
            client = None

        for collection_name in QdrantService.get_collection_names():
            if not connected or client is None:
                collections.append(
                    QdrantCollectionDiagnosticRead(
                        collection_name=collection_name,
                        exists=False,
                        warnings=[
                            "Диагностика коллекции недоступна, "
                            "пока нет соединения с Qdrant."
                        ],
                        error=connection_error,
                    )
                )
                continue

            try:
                exists = bool(client.collection_exists(collection_name))
                if not exists:
                    collections.append(
                        QdrantCollectionDiagnosticRead(
                            collection_name=collection_name,
                            exists=False,
                            warnings=AdminQdrantService._collection_warnings(
                                collection_name,
                                exists=False,
                                points_count=None,
                                provider_matches=None,
                                model_matches=None,
                                vector_size_matches=None,
                            ),
                        )
                    )
                    continue

                info = client.get_collection(collection_name)
                metadata = {
                    str(key): str(value)
                    for key, value in (info.config.metadata or {}).items()
                }
                provider_matches, model_matches, vector_size_matches, metadata_matches = (
                    AdminQdrantService._collection_checks(info)
                )
                points_count = int(info.points_count or 0)
                collections.append(
                    QdrantCollectionDiagnosticRead(
                        collection_name=collection_name,
                        exists=True,
                        status=str(info.status),
                        points_count=points_count,
                        vectors_count=AdminQdrantService._optional_int_attr(
                            info,
                            "vectors_count",
                        ),
                        indexed_vectors_count=AdminQdrantService._optional_int_attr(
                            info,
                            "indexed_vectors_count",
                        ),
                        segments_count=AdminQdrantService._optional_int_attr(
                            info,
                            "segments_count",
                        ),
                        vector_size=QdrantService._extract_vector_size(info),
                        distance=AdminQdrantService._extract_distance(info),
                        metadata=metadata,
                        sample_payload_keys=(
                            QdrantService.get_sample_payload_keys(collection_name)
                            if points_count > 0
                            else []
                        ),
                        provider_matches=provider_matches,
                        model_matches=model_matches,
                        vector_size_matches=vector_size_matches,
                        metadata_matches_active_embeddings=metadata_matches,
                        warnings=AdminQdrantService._collection_warnings(
                            collection_name,
                            exists=True,
                            points_count=points_count,
                            provider_matches=provider_matches,
                            model_matches=model_matches,
                            vector_size_matches=vector_size_matches,
                        ),
                    )
                )
            except Exception as exc:
                collections.append(
                    QdrantCollectionDiagnosticRead(
                        collection_name=collection_name,
                        exists=False,
                        warnings=["Не удалось получить статистику коллекции."],
                        error=str(exc),
                    )
                )

        return QdrantOverviewRead(
            connected=connected,
            connection_error=connection_error,
            qdrant_url=str(embedding_config["qdrant_url"]),
            embedding_provider=(
                str(embedding_config["provider"])
                if embedding_config["provider"] is not None
                else None
            ),
            embedding_model=(
                str(embedding_config["model"])
                if embedding_config["model"] is not None
                else None
            ),
            expected_vector_size=(
                int(embedding_config["vector_size"])
                if embedding_config["vector_size"] is not None
                else None
            ),
            generated_at=generated_at,
            collections=collections,
        )

    @staticmethod
    async def _get_task_or_404(task_id: str, db: AsyncSession) -> Task:
        task = await db.get(Task, task_id)
        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Задача не найдена",
            )
        return task

    @staticmethod
    async def _get_task_in_project_or_404(
        project_id: str,
        task_id: str,
        db: AsyncSession,
    ) -> Task:
        task = await AdminQdrantService._get_task_or_404(task_id, db)
        if task.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Задача не найдена в указанном проекте",
            )
        return task

    @staticmethod
    async def _task_attachments(task_id: str, db: AsyncSession) -> list[TaskAttachment]:
        return list(
            (
                await db.execute(
                    select(TaskAttachment)
                    .where(TaskAttachment.task_id == task_id)
                    .order_by(TaskAttachment.created_at.asc())
                )
            )
            .scalars()
            .all()
        )

    @staticmethod
    async def _load_task_titles(
        task_ids: list[str],
        db: AsyncSession,
    ) -> dict[str, Task]:
        if not task_ids:
            return {}
        rows = list(
            (
                await db.execute(
                    select(Task).where(Task.id.in_(sorted(set(task_ids))))
                )
            )
            .scalars()
            .all()
        )
        return {task.id: task for task in rows}

    @staticmethod
    async def _load_question_context(
        question_ids: list[str],
        db: AsyncSession,
    ) -> dict[str, tuple[ValidationQuestion, Task]]:
        if not question_ids:
            return {}
        rows = (
            await db.execute(
                select(ValidationQuestion, Task)
                .join(Task, Task.id == ValidationQuestion.task_id)
                .where(ValidationQuestion.id.in_(sorted(set(question_ids))))
            )
        ).all()
        return {question.id: (question, task) for question, task in rows}

    @staticmethod
    def _probe_status(
        heuristics: list[QdrantScenarioHeuristicRead],
    ) -> str:
        return "warning" if heuristics else "ok"

    @staticmethod
    async def probe_related_tasks(
        payload: QdrantRelatedTasksProbePayload,
        db: AsyncSession,
    ) -> QdrantScenarioProbeRead:
        task: Task | None = None
        if payload.task_id:
            task = await AdminQdrantService._get_task_in_project_or_404(
                payload.project_id,
                payload.task_id,
                db,
            )

        query_text = (payload.query_text or "").strip()
        if not query_text and task is not None:
            query_text = f"{task.title}\n{task.content}".strip()
        exclude_task_id = payload.exclude_task_id or (task.id if task is not None else None)

        results = (
            await RagService.search_related_tasks(
                db,
                project_id=payload.project_id,
                query_text=query_text,
                exclude_task_id=exclude_task_id,
                limit=payload.limit,
            )
            if query_text
            else []
        )
        indexed_tasks_stmt = (
            select(func.count())
            .select_from(Task)
            .where(Task.project_id == payload.project_id)
            .where(Task.indexed_at.is_not(None))
        )
        if exclude_task_id:
            indexed_tasks_stmt = indexed_tasks_stmt.where(Task.id != exclude_task_id)
        other_indexed_tasks = int(
            (await db.execute(indexed_tasks_stmt)).scalar_one()
        )

        heuristics: list[QdrantScenarioHeuristicRead] = []
        if not query_text:
            heuristics.append(
                QdrantScenarioHeuristicRead(
                    code="query_missing",
                    status="warning",
                    message="Для сценария не удалось собрать текст запроса.",
                )
            )
        if exclude_task_id and any(item.get("task_id") == exclude_task_id for item in results):
            heuristics.append(
                QdrantScenarioHeuristicRead(
                    code="excluded_task_returned",
                    status="warning",
                    message="Поиск вернул задачу, которую ожидалось исключить из выдачи.",
                )
            )
        if not results and other_indexed_tasks > 0:
            heuristics.append(
                QdrantScenarioHeuristicRead(
                    code="empty_results_with_indexed_tasks",
                    status="warning",
                    message=(
                        "В проекте есть другие индексированные задачи, "
                        "но семантический поиск не вернул результатов."
                    ),
                )
            )

        return QdrantScenarioProbeRead(
            scenario="related_tasks",
            project_id=payload.project_id,
            task_id=task.id if task is not None else payload.task_id,
            query_text=query_text,
            heuristic_status=AdminQdrantService._probe_status(heuristics),
            heuristics=heuristics,
            results=[
                QdrantScenarioResultRead(
                    id=str(item["task_id"]),
                    task_id=str(item["task_id"]),
                    task_title=str(item["title"]),
                    task_status=str(item["status"]),
                    score=float(item["score"]),
                    snippet=str(item["title"]),
                    metadata=dict(item),
                )
                for item in results
            ],
        )

    @staticmethod
    async def probe_project_questions(
        payload: QdrantProjectQuestionsProbePayload,
        db: AsyncSession,
    ) -> QdrantScenarioProbeRead:
        task: Task | None = None
        if payload.task_id:
            task = await AdminQdrantService._get_task_in_project_or_404(
                payload.project_id,
                payload.task_id,
                db,
            )

        query_text = (payload.query_text or "").strip()
        if not query_text and task is not None:
            query_text = f"{task.title}\n{task.content}".strip()
        tags = list(payload.tags)
        if not tags and task is not None:
            tags = list(task.tags)

        documents = (
            await QdrantService.search_project_questions(
                project_id=payload.project_id,
                query_text=query_text,
                tags=tags,
                limit=payload.limit,
            )
            if query_text
            else []
        )
        project_question_total = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(ValidationQuestion)
                    .join(Task, Task.id == ValidationQuestion.task_id)
                    .where(Task.project_id == payload.project_id)
                    .where(ValidationQuestion.source == "chat")
                )
            ).scalar_one()
        )
        question_context = await AdminQdrantService._load_question_context(
            [
                str(document.metadata.get("question_id"))
                for document in documents
                if document.metadata.get("question_id")
            ],
            db,
        )

        heuristics: list[QdrantScenarioHeuristicRead] = []
        if not query_text:
            heuristics.append(
                QdrantScenarioHeuristicRead(
                    code="query_missing",
                    status="warning",
                    message="Для сценария не удалось собрать текст запроса.",
                )
            )
        if not documents and project_question_total > 0:
            heuristics.append(
                QdrantScenarioHeuristicRead(
                    code="empty_results_with_project_questions",
                    status="warning",
                    message=(
                        "В проекте есть сохранённые вопросы валидации, "
                        "но поиск не вернул ни одного совпадения."
                    ),
                )
            )

        results: list[QdrantScenarioResultRead] = []
        for index, document in enumerate(documents, start=1):
            question_id = str(document.metadata.get("question_id") or f"question-{index}")
            context = question_context.get(question_id)
            related_task = context[1] if context is not None else None
            results.append(
                QdrantScenarioResultRead(
                    id=question_id,
                    task_id=related_task.id if related_task is not None else None,
                    task_title=related_task.title if related_task is not None else None,
                    task_status=(
                        related_task.status.value if related_task is not None else None
                    ),
                    snippet=str(document.page_content),
                    metadata={key: value for key, value in document.metadata.items()},
                )
            )

        return QdrantScenarioProbeRead(
            scenario="project_questions",
            project_id=payload.project_id,
            task_id=task.id if task is not None else payload.task_id,
            query_text=query_text,
            heuristic_status=AdminQdrantService._probe_status(heuristics),
            heuristics=heuristics,
            results=results,
        )

    @staticmethod
    async def probe_duplicate_proposal(
        payload: QdrantDuplicateProposalProbePayload,
        db: AsyncSession,
    ) -> QdrantScenarioProbeRead:
        if payload.task_id:
            await AdminQdrantService._get_task_in_project_or_404(
                payload.project_id,
                payload.task_id,
                db,
            )

        proposal_text = payload.proposal_text.strip()
        threshold = QdrantService.get_duplicate_proposal_threshold()
        near_threshold = max(threshold - _DUPLICATE_PROPOSAL_NEAR_THRESHOLD_DELTA, 0.0)
        hits = await QdrantService.probe_duplicate_proposals(
            project_id=payload.project_id,
            proposal_text=proposal_text,
            limit=3,
        )
        task_map = await AdminQdrantService._load_task_titles(
            [
                str(item["task_id"])
                for item in hits
                if item.get("task_id") is not None
            ],
            db,
        )
        proposal_rows = (
            await db.execute(
                select(ChangeProposal).where(
                    ChangeProposal.id.in_(
                        [
                            str(item["proposal_id"])
                            for item in hits
                            if item.get("proposal_id") is not None
                        ]
                    )
                )
            )
        ).scalars().all()
        proposal_map = {proposal.id: proposal for proposal in proposal_rows}

        heuristics: list[QdrantScenarioHeuristicRead] = []
        if hits:
            top_score = float(hits[0]["score"])
            if top_score < threshold and top_score >= near_threshold:
                heuristics.append(
                    QdrantScenarioHeuristicRead(
                    code="near_threshold_duplicate",
                    status="warning",
                    message=(
                        "Найдено очень похожее предложение, "
                        "но его score чуть ниже рабочего порога дубликатов."
                    ),
                )
            )

        results: list[QdrantScenarioResultRead] = []
        for item in hits:
            task_id = str(item.get("task_id") or "")
            task = task_map.get(task_id)
            proposal_id = str(item.get("proposal_id") or "")
            proposal = proposal_map.get(proposal_id)
            score = float(item["score"])
            if score >= threshold:
                match_band = "above_threshold"
            elif score >= near_threshold:
                match_band = "near_threshold"
            else:
                match_band = "below_threshold"
            results.append(
                QdrantScenarioResultRead(
                    id=proposal_id or task_id or "proposal-match",
                    task_id=task.id if task is not None else None,
                    task_title=task.title if task is not None else None,
                    task_status=task.status.value if task is not None else None,
                    score=score,
                    snippet=str(item["proposal_text"]),
                    metadata={
                        "proposal_id": proposal_id or None,
                        "status": (
                            proposal.status.value
                            if proposal is not None
                            else item.get("status")
                        ),
                    },
                    match_band=match_band,
                )
            )

        return QdrantScenarioProbeRead(
            scenario="duplicate_proposal",
            project_id=payload.project_id,
            task_id=payload.task_id,
            query_text=proposal_text,
            heuristic_status=AdminQdrantService._probe_status(heuristics),
            heuristics=heuristics,
            results=results,
            raw_threshold=threshold,
        )

    @staticmethod
    async def get_project_coverage(
        project_id: str,
        db: AsyncSession,
        *,
        limit: int = 20,
    ) -> QdrantProjectCoverageRead:
        project = await ProjectService.get_project_or_404(project_id, db)
        tasks = list(
            (
                await db.execute(
                    select(Task)
                    .where(Task.project_id == project_id)
                    .order_by(Task.updated_at.desc(), Task.created_at.desc())
                )
            )
            .scalars()
            .all()
        )

        question_counts = {
            str(task_id): int(total)
            for task_id, total in (
                await db.execute(
                    select(
                        ValidationQuestion.task_id,
                        func.count(ValidationQuestion.id),
                    )
                    .join(Task, Task.id == ValidationQuestion.task_id)
                    .where(Task.project_id == project_id)
                    .where(ValidationQuestion.source == "chat")
                    .group_by(ValidationQuestion.task_id)
                )
            ).all()
        }

        knowledge_counts: dict[str, int] = {}
        qdrant_question_counts: dict[str, int] = {}
        for task in tasks:
            knowledge_counts[task.id] = QdrantService.count_points(
                TASK_KNOWLEDGE_COLLECTION,
                filter_=AdminQdrantService._task_filter(task.id),
            )
            qdrant_question_counts[task.id] = QdrantService.count_points(
                PROJECT_QUESTIONS_COLLECTION,
                filter_=AdminQdrantService._task_filter(task.id),
            )

        items = [
            QdrantCoverageTaskRead(
                id=task.id,
                title=task.title,
                status=task.status,
                indexed_at=task.indexed_at,
                updated_at=task.updated_at,
                embeddings_stale=TaskService._has_stale_embeddings(task),
                requires_revalidation=TaskService._requires_revalidation(task),
                validation_questions_total=question_counts.get(task.id, 0),
                knowledge_points_count=knowledge_counts.get(task.id, 0),
                question_points_count=qdrant_question_counts.get(task.id, 0),
            )
            for task in tasks[:limit]
        ]

        return QdrantProjectCoverageRead(
            project_id=project.id,
            project_name=project.name,
            generated_at=datetime.now(UTC),
            summary=QdrantProjectCoverageSummaryRead(
                tasks_total=len(tasks),
                indexed_tasks_total=sum(task.indexed_at is not None for task in tasks),
                stale_tasks_total=sum(
                    TaskService._has_stale_embeddings(task) for task in tasks
                ),
                tasks_with_knowledge_total=sum(
                    count > 0 for count in knowledge_counts.values()
                ),
                tasks_with_questions_total=sum(
                    count > 0 for count in qdrant_question_counts.values()
                ),
            ),
            items=items,
        )

    @staticmethod
    async def resync_task(
        task_id: str,
        current_user: User,
        db: AsyncSession,
    ) -> QdrantTaskResyncRead:
        task = await AdminQdrantService._get_task_or_404(task_id, db)
        attachments = await AdminQdrantService._task_attachments(task.id, db)
        attachment_payloads = await AttachmentContentService.build_attachment_payloads(
            db,
            task,
            attachments,
            actor_user_id=current_user.id,
            allow_vision=False,
        )

        warnings: list[str] = []
        for attachment, payload in zip(attachments, attachment_payloads, strict=False):
            if (
                AttachmentContentService.is_image(attachment.content_type)
                and not payload.get("alt_text")
            ):
                warnings.append(
                    f"У вложения {attachment.filename} нет сохранённого alt-text, "
                    "поэтому индекс пересобран без vision-описания."
                )
            if (
                AttachmentContentService.is_text(attachment.content_type)
                and not payload.get("extracted_text")
            ):
                warnings.append(
                    f"У вложения {attachment.filename} не удалось прочитать "
                    "текстовое содержимое из сохранённого файла."
                )

        chunk_ids = await RagService.index_task_context(
            db,
            task,
            attachments,
            actor_user_id=current_user.id,
            attachment_payloads=attachment_payloads,
            allow_vision=False,
            validation_result=task.validation_result,
        )
        await ValidationQuestionService.sync_project_questions_index(task, db)
        if not chunk_ids:
            warnings.append(
                "Qdrant не вернул новых chunk ids для knowledge-индекса. "
                "Проверьте конфигурацию коллекции и содержимое задачи."
            )

        AuditService.record(
            db,
            actor_user_id=current_user.id,
            event_type="admin.qdrant_task_resynced",
            entity_type="task",
            entity_id=task.id,
            project_id=task.project_id,
            task_id=task.id,
            metadata={"warnings_total": len(warnings), "chunk_ids_total": len(chunk_ids)},
        )
        await db.commit()
        await db.refresh(task)

        return QdrantTaskResyncRead(
            task_id=task.id,
            project_id=task.project_id,
            indexed_at=task.indexed_at,
            embeddings_stale=TaskService._has_stale_embeddings(task),
            knowledge_points_count=QdrantService.count_points(
                TASK_KNOWLEDGE_COLLECTION,
                filter_=AdminQdrantService._task_filter(task.id),
            ),
            question_points_count=QdrantService.count_points(
                PROJECT_QUESTIONS_COLLECTION,
                filter_=AdminQdrantService._task_filter(task.id),
            ),
            chunk_ids=chunk_ids,
            warnings=warnings,
        )
