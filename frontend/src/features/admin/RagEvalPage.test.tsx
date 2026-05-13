import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import RagEvalPage from "@/features/admin/RagEvalPage";

const adminApiMock = vi.hoisted(() => ({
  createRagEvalRun: vi.fn(),
  exportRagEvalRun: vi.fn(),
  getRagEvalDataset: vi.fn(),
  getRagEvalRun: vi.fn(),
  importRagEvalDataset: vi.fn(),
  listRagEvalDatasets: vi.fn(),
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
    projectsApiMock.list.mockResolvedValue([
      {
        id: "project-1",
        name: "Eval Project",
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
    adminApiMock.listRagEvalDatasets.mockResolvedValue([
      {
        id: "dataset-1",
        project_id: "project-1",
        project_name: "Eval Project",
        name: "RAG eval set",
        tasks_total: 1,
        cases_total: 1,
        last_run_id: null,
        last_run_status: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    ]);
    adminApiMock.getRagEvalDataset.mockResolvedValue({
      id: "dataset-1",
      project_id: "project-1",
      project_name: "Eval Project",
      name: "RAG eval set",
      tasks_total: 1,
      cases_total: 1,
      last_run_id: null,
      last_run_status: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      tasks: [
        {
          id: "mapping-1",
          external_id: "task-auth-1",
          task_id: "task-1",
          title: "Авторизация",
          updated_at: new Date().toISOString(),
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
          updated_at: new Date().toISOString(),
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
        last_run_id: null,
        last_run_status: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
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
        min_score_override: null,
      },
      created_at: new Date().toISOString(),
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
        min_score_override: null,
      },
      summary_metrics: {
        recall_at_5: 1,
        mrr: 1,
        total_tokens: 42,
      },
      started_at: new Date().toISOString(),
      finished_at: new Date().toISOString(),
      latency_ms: 100,
      error_message: null,
      created_at: new Date().toISOString(),
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
          retrieved_chunks: [],
          matched_expected: [],
          answer_text: "Ответ подтвержден.",
          answer_source_ref: null,
          judge_payload: { correctness: "correct" },
          metrics: { recall_at_5: true, mrr: 1, correctness: "correct" },
          latency_ms: 100,
          retrieval_latency_ms: 20,
          answer_latency_ms: 50,
          judge_latency_ms: 30,
          error_message: null,
          created_at: new Date().toISOString(),
        },
      ],
    });
    adminApiMock.exportRagEvalRun.mockResolvedValue("case_external_id\ncase-1\n");
  });

  it("imports a JSON dataset and starts a RAG Eval run", async () => {
    render(<RagEvalPage />);

    expect(await screen.findByText("Оценка качества RAG")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Импортировать набор" }));

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
        expect.objectContaining({ use_query_rewriter: true }),
      );
    });

    expect(await screen.findByText("Готово")).toBeInTheDocument();
    expect(screen.getByText("case-1")).toBeInTheDocument();
  });
});
