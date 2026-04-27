import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import QdrantAdminPage from "@/features/admin/QdrantAdminPage";

const adminApiMock = vi.hoisted(() => ({
  getQdrantOverview: vi.fn(),
  getQdrantProjectCoverage: vi.fn(),
  probeQdrantDuplicateProposal: vi.fn(),
  probeQdrantProjectQuestions: vi.fn(),
  probeQdrantRelatedTasks: vi.fn(),
  resyncQdrantTask: vi.fn(),
}));

const projectsApiMock = vi.hoisted(() => ({
  list: vi.fn(),
}));

const tasksApiMock = vi.hoisted(() => ({
  list: vi.fn(),
}));

vi.mock("@/api/adminApi", () => ({
  adminApi: adminApiMock,
}));

vi.mock("@/api/projectsApi", () => ({
  projectsApi: projectsApiMock,
}));

vi.mock("@/api/tasksApi", () => ({
  tasksApi: tasksApiMock,
}));

describe("QdrantAdminPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    adminApiMock.getQdrantOverview.mockResolvedValue({
      connected: true,
      connection_error: null,
      qdrant_url: "http://localhost:6333",
      embedding_provider: "openai",
      embedding_model: "text-embedding-3-small",
      expected_vector_size: 1536,
      generated_at: new Date().toISOString(),
      collections: [
        {
          collection_name: "task_knowledge",
          exists: true,
          status: "green",
          points_count: 12,
          vectors_count: 12,
          indexed_vectors_count: 12,
          segments_count: 1,
          vector_size: 1536,
          distance: "Cosine",
          metadata: {
            embedding_provider: "openai",
            embedding_model: "text-embedding-3-small",
          },
          sample_payload_keys: ["task_id", "task_title"],
          provider_matches: true,
          model_matches: true,
          vector_size_matches: true,
          metadata_matches_active_embeddings: true,
          warnings: [],
          error: null,
        },
      ],
    });
    projectsApiMock.list.mockResolvedValue([
      {
        id: "project-1",
        name: "Alpha",
        description: null,
        created_by: "admin-1",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        validation_node_settings: {
          core_rules: true,
          custom_rules: true,
          context_questions: true,
        },
      },
    ]);
    tasksApiMock.list.mockResolvedValue([
      {
        id: "task-1",
        project_id: "project-1",
        title: "Синхронизация статусов",
        content: "Нужно выровнять статусы между системами.",
        tags: ["integration"],
        status: "in_progress",
        created_by: "admin-1",
        analyst_id: "admin-1",
        developer_id: null,
        tester_id: null,
        validation_result: null,
        attachments: [],
        indexed_at: new Date().toISOString(),
        embeddings_stale: false,
        requires_revalidation: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    ]);
    adminApiMock.getQdrantProjectCoverage.mockResolvedValue({
      project_id: "project-1",
      project_name: "Alpha",
      generated_at: new Date().toISOString(),
      summary: {
        tasks_total: 1,
        indexed_tasks_total: 1,
        stale_tasks_total: 0,
        tasks_with_knowledge_total: 1,
        tasks_with_questions_total: 1,
      },
      items: [
        {
          id: "task-1",
          title: "Синхронизация статусов",
          status: "in_progress",
          indexed_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          embeddings_stale: false,
          requires_revalidation: false,
          validation_questions_total: 1,
          knowledge_points_count: 4,
          question_points_count: 2,
        },
      ],
    });
    adminApiMock.probeQdrantRelatedTasks.mockResolvedValue({
      scenario: "related_tasks",
      project_id: "project-1",
      task_id: "task-1",
      query_text: "Синхронизация статусов",
      heuristic_status: "warning",
      heuristics: [
        {
          code: "empty_results_with_indexed_tasks",
          status: "warning",
          message: "В проекте есть другие индексированные задачи.",
        },
      ],
      results: [
        {
          id: "task-2",
          task_id: "task-2",
          task_title: "Экспорт статусов",
          task_status: "ready_for_dev",
          score: 0.9342,
          snippet: "Экспорт статусов во внешнюю систему.",
          metadata: { source: "task_knowledge" },
          match_band: null,
        },
      ],
      raw_threshold: null,
    });
    adminApiMock.resyncQdrantTask.mockResolvedValue({
      task_id: "task-1",
      project_id: "project-1",
      indexed_at: new Date().toISOString(),
      embeddings_stale: false,
      knowledge_points_count: 5,
      question_points_count: 2,
      chunk_ids: ["chunk-1"],
      warnings: ["У вложения diagram.png нет сохранённого alt-text."],
    });
  });

  it("renders overview diagnostics and collection details", async () => {
    render(<QdrantAdminPage />);

    expect(
      await screen.findByText("Проверка качества Qdrant и RAG-сценариев"),
    ).toBeInTheDocument();
    expect(screen.getByText("task_knowledge")).toBeInTheDocument();
    expect(screen.getByText("openai")).toBeInTheDocument();
  });

  it("runs the related tasks scenario and renders heuristic results", async () => {
    render(<QdrantAdminPage />);

    await screen.findByText("task_knowledge");
    fireEvent.click(screen.getByRole("button", { name: "Сценарии" }));
    fireEvent.click(screen.getByRole("button", { name: "Запустить сценарий" }));

    await waitFor(() => {
      expect(adminApiMock.probeQdrantRelatedTasks).toHaveBeenCalledWith({
        project_id: "project-1",
        task_id: "task-1",
        query_text: undefined,
        exclude_task_id: "task-1",
        limit: 5,
      });
    });

    expect(await screen.findByText("Экспорт статусов")).toBeInTheDocument();
    expect(
      screen.getByText("В проекте есть другие индексированные задачи."),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Частично" }));
    expect(screen.getByRole("button", { name: "Частично" })).toHaveClass(
      "ui-button-primary",
    );
  });

  it("resyncs a task from the coverage tab and shows warnings", async () => {
    render(<QdrantAdminPage />);

    await screen.findByText("task_knowledge");
    fireEvent.click(screen.getByRole("button", { name: "Покрытие" }));

    const resyncButton = await screen.findByRole("button", {
      name: "Пересинхронизировать индекс",
    });
    fireEvent.click(resyncButton);

    await waitFor(() => {
      expect(adminApiMock.resyncQdrantTask).toHaveBeenCalledWith("task-1");
    });

    expect(await screen.findByText("Индекс задачи пересобран")).toBeInTheDocument();
    expect(
      screen.getByText("У вложения diagram.png нет сохранённого alt-text."),
    ).toBeInTheDocument();
  });
});
