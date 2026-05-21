import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import RagEvalPage from "@/features/admin/RagEvalPage";

const adminApiMock = vi.hoisted(() => ({
  createRagEvalRun: vi.fn(),
  deleteRagEvalRun: vi.fn(),
  exportRagEvalRun: vi.fn(),
  getRagEvalDataset: vi.fn(),
  getRagEvalRun: vi.fn(),
  importRagEvalDataset: vi.fn(),
  listRagEvalDatasets: vi.fn(),
  listRagEvalRuns: vi.fn(),
}));

const projectsApiMock = vi.hoisted(() => ({
  list: vi.fn(),
}));

vi.mock("@/api/adminApi", () => ({
  adminApi: adminApiMock,
}));

vi.mock("@/api/projectsApi", () => ({
  projectsApi: projectsApiMock,
}));

describe("RagEvalPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    const now = new Date().toISOString();
    projectsApiMock.list.mockResolvedValue([
      {
        id: "project-1",
        name: "Eval Project",
        description: null,
        created_by: "admin-1",
        created_at: now,
        updated_at: now,
        validation_node_settings: {
          core_rules: true,
          custom_rules: true,
          context_questions: true,
        },
      },
    ]);
    adminApiMock.listRagEvalDatasets.mockResolvedValue([
      {
        id: "dataset-1",
        project_id: "project-1",
        project_name: "Eval Project",
        name: "RAG eval set",
        tasks_total: 1,
        cases_total: 1,
        last_run_id: "run-1",
        last_run_status: "success",
        created_at: now,
        updated_at: now,
      },
    ]);
    adminApiMock.getRagEvalDataset.mockResolvedValue({
      id: "dataset-1",
      project_id: "project-1",
      project_name: "Eval Project",
      name: "RAG eval set",
      tasks_total: 1,
      cases_total: 1,
      last_run_id: "run-1",
      last_run_status: "success",
      created_at: now,
      updated_at: now,
      tasks: [
        {
          id: "mapping-1",
          external_id: "task-auth-1",
          task_id: "task-1",
          title: "Авторизация",
          updated_at: now,
        },
      ],
      cases: [
        {
          id: "case-1",
          external_id: "case-1",
          task_external_id: "task-auth-1",
          task_id: "task-1",
          question: "Какие требования к авторизации?",
          expected_answer: "Ответ",
          expected_relevant: [],
          updated_at: now,
        },
      ],
    });
    adminApiMock.importRagEvalDataset.mockResolvedValue({
      dataset: {
        id: "dataset-1",
        project_id: "project-1",
        project_name: "Eval Project",
        name: "RAG eval set",
        tasks_total: 1,
        cases_total: 1,
        last_run_id: "run-1",
        last_run_status: "success",
        created_at: now,
        updated_at: now,
        tasks: [],
        cases: [],
      },
      created_tasks: 1,
      updated_tasks: 0,
      imported_cases: 1,
      warnings: [],
    });
    adminApiMock.createRagEvalRun.mockResolvedValue({
      id: "run-1",
      dataset_id: "dataset-1",
      status: "queued",
      config: {
        indexing_mode: "all",
        retrieval_limit: 5,
        use_query_rewriter: true,
        use_hybrid_rerank: true,
        include_cross_task: true,
        include_current_task_content: false,
        run_answer_agent: true,
        run_llm_judge: true,
        run_bm25_baseline: true,
        min_score_override: null,
      },
      created_at: now,
    });
    adminApiMock.listRagEvalRuns.mockResolvedValue({
      page: 1,
      page_size: 10,
      total: 1,
      items: [
        {
          id: "run-1",
          dataset_id: "dataset-1",
          dataset_name: "RAG eval set",
          project_id: "project-1",
          status: "success",
          config: {
            indexing_mode: "all",
            retrieval_limit: 5,
            use_query_rewriter: true,
            use_hybrid_rerank: true,
            include_cross_task: true,
            include_current_task_content: false,
            run_answer_agent: true,
            run_llm_judge: true,
            run_bm25_baseline: true,
            min_score_override: null,
          },
          summary_metrics: {
            recall_at_5: 1,
            mrr: 1,
            bm25_recall_at_5: 1,
            bm25_mrr: 1,
            rag_vs_bm25_mrr_delta: 0,
            correctness: { correct: 1 },
          },
          started_at: now,
          finished_at: now,
          latency_ms: 100,
          error_message: null,
          created_at: now,
        },
      ],
    });
    adminApiMock.getRagEvalRun.mockResolvedValue({
      id: "run-1",
      dataset_id: "dataset-1",
      dataset_name: "RAG eval set",
      project_id: "project-1",
      status: "success",
      config: {
        indexing_mode: "all",
        retrieval_limit: 5,
        use_query_rewriter: true,
        use_hybrid_rerank: true,
        include_cross_task: true,
        include_current_task_content: false,
        run_answer_agent: true,
        run_llm_judge: true,
        run_bm25_baseline: true,
        min_score_override: null,
      },
      summary_metrics: {
        recall_at_5: 1,
        mrr: 1,
        bm25_recall_at_5: 1,
        bm25_mrr: 1,
        rag_vs_bm25_mrr_delta: 0,
        total_tokens: 42,
        correctness: { correct: 1 },
      },
      started_at: now,
      finished_at: now,
      latency_ms: 100,
      error_message: null,
      created_at: now,
      index_results: [],
      case_results: [
        {
          id: "result-1",
          case_id: "case-1",
          case_external_id: "case-1",
          question: "Какие требования к авторизации?",
          task_id: "task-1",
          task_external_id: "task-auth-1",
          status: "success",
          retrieved_chunks: [
            {
              chunk_id: "chunk-1",
              task_id: "task-1",
              task_external_id: "task-auth-1",
              source_type: "task_content",
              chunk_index: 0,
              score: 0.91,
              threshold: 0.3,
              content: "Описание задачи с корректной русской кодировкой.",
            },
          ],
          matched_expected: [
            {
              chunk_id: "chunk-1",
              rank: 1,
              text_contains: "русской кодировкой",
            },
          ],
          answer_text: "Ответ подтвержден.",
          answer_source_ref: null,
          judge_payload: {
            correctness: "correct",
            groundedness: "grounded",
            rationale: "Ответ подтверждён.",
            unsupported_claims: [],
          },
          metrics: {
            recall_at_5: true,
            mrr: 1,
            correctness: "correct",
            groundedness: "grounded",
            first_relevant_rank: 1,
            bm25_recall_at_5: true,
            bm25_precision_at_k: 0.2,
            bm25_mrr: 1,
            bm25_first_relevant_rank: 1,
            rag_vs_bm25_mrr_delta: 0,
            bm25_retrieved_chunks: [
              {
                chunk_id: "chunk-1",
                task_id: "task-1",
                task_external_id: "task-auth-1",
                source_type: "task_content",
                chunk_index: 0,
                score: 1.2,
                content: "Описание задачи с корректной русской кодировкой.",
              },
            ],
            bm25_matched_expected: [
              {
                chunk_id: "chunk-1",
                rank: 1,
                text_contains: "русской кодировкой",
              },
            ],
            no_context: false,
          },
          latency_ms: 100,
          retrieval_latency_ms: 20,
          answer_latency_ms: 50,
          judge_latency_ms: 30,
          error_message: null,
          created_at: now,
        },
      ],
    });
    adminApiMock.exportRagEvalRun.mockResolvedValue(
      "case_external_id\ncase-1\n",
    );
    adminApiMock.deleteRagEvalRun.mockResolvedValue(undefined);
  });

  it("imports a JSON dataset and starts a RAG Eval run", async () => {
    render(<RagEvalPage />);

    expect(await screen.findByText("Оценка качества RAG")).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Импортировать набор" }),
    );

    await waitFor(() => {
      expect(adminApiMock.importRagEvalDataset).toHaveBeenCalledWith({
        format: "json",
        content: expect.stringContaining("RAG eval set"),
      });
    });

    expect(await screen.findByText(/Импортировано/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Запустить RAG Eval" }));

    await waitFor(() => {
      expect(adminApiMock.createRagEvalRun).toHaveBeenCalledWith(
        "dataset-1",
        expect.objectContaining({
          run_bm25_baseline: true,
          use_query_rewriter: true,
        }),
      );
    });

    expect((await screen.findAllByText("Готово")).length).toBeGreaterThan(0);
    expect(screen.getByText("case-1")).toBeInTheDocument();
  });

  it("opens a saved run from history and renders retrieval details as UI", async () => {
    render(<RagEvalPage />);

    expect(await screen.findByText("Оценка качества RAG")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Запуск" }));

    expect(await screen.findByText("История запусков")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Открыть" }));

    await waitFor(() => {
      expect(adminApiMock.getRagEvalRun).toHaveBeenCalledWith("run-1");
    });

    fireEvent.click(await screen.findByText("Retrieval details"));

    expect(screen.getByText("Retrieved chunks")).toBeInTheDocument();
    expect(screen.getByText("BM25 retrieved chunks")).toBeInTheDocument();
    expect(screen.getByText("Matched expected")).toBeInTheDocument();
    expect(screen.getByText("Judge result")).toBeInTheDocument();
    expect(
      screen.getAllByText("Описание задачи с корректной русской кодировкой.")
        .length,
    ).toBeGreaterThan(0);
    expect(screen.queryByText(/"retrieved_chunks"/)).not.toBeInTheDocument();
  });

  it("filters and sorts case results on the opened run", async () => {
    const defaultRun = await adminApiMock.getRagEvalRun();
    adminApiMock.getRagEvalRun.mockClear();
    adminApiMock.getRagEvalRun.mockResolvedValueOnce({
      ...defaultRun,
      case_results: [
        {
          id: "result-1",
          case_id: "case-1",
          case_external_id: "case-1",
          question: "Какие требования к авторизации?",
          task_id: "task-1",
          task_external_id: "task-auth-1",
          status: "success",
          retrieved_chunks: [],
          matched_expected: [],
          answer_text: "Ответ подтвержден.",
          answer_source_ref: null,
          judge_payload: { correctness: "correct", groundedness: "grounded" },
          metrics: {
            recall_at_5: true,
            mrr: 1,
            correctness: "correct",
            groundedness: "grounded",
            no_context: false,
          },
          latency_ms: 100,
          retrieval_latency_ms: 20,
          answer_latency_ms: 50,
          judge_latency_ms: 30,
          error_message: null,
          created_at: "2026-05-13T10:00:00.000Z",
        },
        {
          id: "result-2",
          case_id: "case-2",
          case_external_id: "case-2",
          question: "Что делать без контекста?",
          task_id: "task-1",
          task_external_id: "task-auth-1",
          status: "success",
          retrieved_chunks: [],
          matched_expected: [],
          answer_text: "Контекст не найден.",
          answer_source_ref: null,
          judge_payload: {
            correctness: "not_enough_context",
            groundedness: "unsupported",
          },
          metrics: {
            recall_at_5: false,
            mrr: 0,
            correctness: "not_enough_context",
            groundedness: "unsupported",
            no_context: true,
          },
          latency_ms: 90,
          retrieval_latency_ms: 5,
          answer_latency_ms: 50,
          judge_latency_ms: 30,
          error_message: null,
          created_at: "2026-05-13T11:00:00.000Z",
        },
      ],
    });

    render(<RagEvalPage />);

    expect(await screen.findByText("Оценка качества RAG")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Запуск" }));
    fireEvent.click(await screen.findByRole("button", { name: "Открыть" }));

    expect(await screen.findByText("case-1")).toBeInTheDocument();
    expect(screen.getByText("case-2")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Recall@5"), {
      target: { value: "miss" },
    });

    expect(screen.queryByText("case-1")).not.toBeInTheDocument();
    expect(screen.getByText("case-2")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Сортировка"), {
      target: { value: "retrieval_latency_ms" },
    });
    fireEvent.change(screen.getByLabelText("Направление"), {
      target: { value: "desc" },
    });

    expect(adminApiMock.getRagEvalRun).toHaveBeenCalledTimes(1);
  });

  it("deletes a saved run after confirmation and refreshes history", async () => {
    render(<RagEvalPage />);

    expect(await screen.findByText("Оценка качества RAG")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Запуск" }));
    expect(await screen.findByText("История запусков")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Удалить" }));
    fireEvent.click(screen.getByRole("button", { name: "Удалить запуск" }));

    await waitFor(() => {
      expect(adminApiMock.deleteRagEvalRun).toHaveBeenCalledWith("run-1");
    });
    expect(adminApiMock.listRagEvalRuns).toHaveBeenCalledWith("dataset-1", {
      page: 1,
      size: 10,
    });
  });
});
