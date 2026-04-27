from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.task import TaskStatus

QdrantScenario = Literal["related_tasks", "project_questions", "duplicate_proposal"]
QdrantHeuristicStatus = Literal["ok", "warning"]


class QdrantOverviewRead(BaseModel):
    connected: bool
    connection_error: str | None = None
    qdrant_url: str
    embedding_provider: str | None = None
    embedding_model: str | None = None
    expected_vector_size: int | None = None
    generated_at: datetime
    collections: list[QdrantCollectionDiagnosticRead]


class QdrantCollectionDiagnosticRead(BaseModel):
    collection_name: str
    exists: bool
    status: str | None = None
    points_count: int | None = None
    vectors_count: int | None = None
    indexed_vectors_count: int | None = None
    segments_count: int | None = None
    vector_size: int | None = None
    distance: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
    sample_payload_keys: list[str] = Field(default_factory=list)
    provider_matches: bool | None = None
    model_matches: bool | None = None
    vector_size_matches: bool | None = None
    metadata_matches_active_embeddings: bool | None = None
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


class QdrantScenarioHeuristicRead(BaseModel):
    code: str
    status: QdrantHeuristicStatus
    message: str


class QdrantScenarioResultRead(BaseModel):
    id: str
    task_id: str | None = None
    task_title: str | None = None
    task_status: str | None = None
    score: float | None = None
    snippet: str
    metadata: dict[str, Any] | None = None
    match_band: Literal["above_threshold", "near_threshold", "below_threshold"] | None = None


class QdrantScenarioProbeRead(BaseModel):
    scenario: QdrantScenario
    project_id: str
    task_id: str | None = None
    query_text: str
    heuristic_status: QdrantHeuristicStatus
    heuristics: list[QdrantScenarioHeuristicRead] = Field(default_factory=list)
    results: list[QdrantScenarioResultRead] = Field(default_factory=list)
    raw_threshold: float | None = None


class QdrantRelatedTasksProbePayload(BaseModel):
    project_id: str
    task_id: str | None = None
    query_text: str | None = None
    exclude_task_id: str | None = None
    limit: int = Field(default=3, ge=1, le=10)

    model_config = ConfigDict(extra="forbid")


class QdrantProjectQuestionsProbePayload(BaseModel):
    project_id: str
    task_id: str | None = None
    query_text: str | None = None
    tags: list[str] = Field(default_factory=list)
    limit: int = Field(default=5, ge=1, le=10)

    model_config = ConfigDict(extra="forbid")


class QdrantDuplicateProposalProbePayload(BaseModel):
    project_id: str
    proposal_text: str = Field(min_length=1)
    task_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class QdrantCoverageTaskRead(BaseModel):
    id: str
    title: str
    status: TaskStatus
    indexed_at: datetime | None = None
    updated_at: datetime
    embeddings_stale: bool
    requires_revalidation: bool
    validation_questions_total: int
    knowledge_points_count: int
    question_points_count: int

    model_config = ConfigDict(use_enum_values=True)


class QdrantProjectCoverageSummaryRead(BaseModel):
    tasks_total: int
    indexed_tasks_total: int
    stale_tasks_total: int
    tasks_with_knowledge_total: int
    tasks_with_questions_total: int


class QdrantProjectCoverageRead(BaseModel):
    project_id: str
    project_name: str
    generated_at: datetime
    summary: QdrantProjectCoverageSummaryRead
    items: list[QdrantCoverageTaskRead]


class QdrantTaskResyncRead(BaseModel):
    task_id: str
    project_id: str
    indexed_at: datetime | None = None
    embeddings_stale: bool
    knowledge_points_count: int
    question_points_count: int
    chunk_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
