import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AdaptationEvalPage from "@/features/admin/AdaptationEvalPage";

const adminApiMock = vi.hoisted(() => ({
  createAdaptationEvalRun: vi.fn(),
  deleteAdaptationEvalDataset: vi.fn(),
  deleteAdaptationEvalRun: vi.fn(),
  exportAdaptationEvalRun: vi.fn(),
  getAdaptationEvalDataset: vi.fn(),
  getAdaptationEvalRun: vi.fn(),
  importAdaptationEvalDataset: vi.fn(),
  listAdaptationEvalDatasets: vi.fn(),
  listAdaptationEvalRuns: vi.fn(),
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

describe("AdaptationEvalPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:adaptation-eval"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    Object.defineProperty(HTMLAnchorElement.prototype, "click", {
      configurable: true,
      value: vi.fn(),
    });

    const now = "2026-05-18T10:00:00.000Z";
    const dataset = {
      cases_total: 1,
      created_at: now,
      id: "dataset-1",
      last_run_id: "run-1",
      last_run_status: "success",
      name: "Adaptation eval set",
      project_id: "project-1",
      project_name: "Eval Project",
      updated_at: now,
    };
    const caseItem = {
      expected_captured_questions: [
        "Какие роли пользователей должны поддерживаться?",
      ],
      expected_context_issues: [
        {
          code: "context_question",
          message: "Какие роли пользователей должны поддерживаться?",
          severity: "medium",
          source: "context_questions",
        },
      ],
      expected_context_questions: [
        "Какие роли пользователей должны поддерживаться?",
      ],
      expected_retrieved_questions: [
        "Какие роли пользователей должны поддерживаться?",
      ],
      expected_verdict: "needs_rework",
      external_id: "adapt-auth-positive",
      historical_tasks: [
        {
          chat_messages: ["Какие роли пользователей должны поддерживаться?"],
          content: "Нужно описать вход.",
          tags: ["auth"],
          title: "Авторизация",
        },
      ],
      id: "case-1",
      metadata: { scenario: "positive" },
      probe_task: {
        content: "Нужно реализовать вход.",
        tags: ["auth"],
        title: "Вход в кабинет",
      },
      scenario_type: "positive",
      updated_at: now,
    };
    const config = {
      cleanup_synthetic_tasks: true,
      judge_match_confidence_min: 0.75,
      quality_gates: {
        capture_recall_min: 0.95,
        context_issue_f1_min: 0.7,
        context_question_f1_min: 0.75,
        duplicate_rate_max: 0.1,
        retrieval_recall_at_k_min: 0.8,
      },
      retrieval_limit: 5,
      run_match_judge: true,
    };
    const runDetail = {
      case_results: [
        {
          actual_result: {
            captured_questions: [
              "Какие роли пользователей должны поддерживаться?",
            ],
            context_validation: {
              context_questions: [
                "Какие роли пользователей должны поддерживаться?",
              ],
              issues: [
                {
                  code: "context_question",
                  message: "Какие роли пользователей должны поддерживаться?",
                  source: "context_questions",
                },
              ],
              verdict: "needs_rework",
            },
            retrieval_results: [
              {
                question_text:
                  "Какие роли пользователей должны поддерживаться?",
                rank: 1,
                score: 0.96,
              },
            ],
          },
          case_external_id: "adapt-auth-positive",
          case_id: "case-1",
          core_graph_run_id: null,
          created_at: now,
          diffs: {
            capture_match_source: { deterministic: 1, judge: 0 },
            context_issue_match_source: { deterministic: 1, judge: 0 },
            context_question_match_source: { deterministic: 1, judge: 0 },
            retrieval_match_source: { deterministic: 1, judge: 0 },
          },
          error_message: null,
          expected_result: {},
          full_graph_run_id: null,
          id: "result-1",
          latency_ms: 100,
          metrics: {
            capture_recall: 1,
            context_issue_f1: 1,
            context_question_f1: 1,
            context_question_text_f1: 1,
            overall_question_duplicate_rate: 0,
            retrieval_mrr: 1,
            retrieval_recall_at_k: 1,
          },
          scenario_type: "positive",
          status: "passed",
          synthetic_task_ids: ["task-1", "task-2"],
        },
      ],
      config,
      created_at: now,
      dataset_id: "dataset-1",
      dataset_name: "Adaptation eval set",
      error_message: null,
      finished_at: now,
      id: "run-1",
      latency_ms: 240,
      project_id: "project-1",
      started_at: now,
      status: "success",
      summary_metrics: {
        capture_recall: 1,
        cases_total: 1,
        context_issue_f1: 1,
        context_question_f1: 1,
        gate_status: "passed",
        pass_rate: 1,
        quality_gates: [
          {
            key: "capture_recall",
            label: "Capture recall",
            passed: true,
            threshold: 0.95,
            value: 1,
          },
        ],
        retrieval_recall_at_k: 1,
      },
    };

    projectsApiMock.list.mockResolvedValue([
      {
        created_at: now,
        created_by: "admin-1",
        description: null,
        id: "project-1",
        name: "Eval Project",
        updated_at: now,
        validation_node_settings: {
          context_questions: true,
          core_rules: true,
          custom_rules: true,
        },
      },
    ]);
    adminApiMock.listAdaptationEvalDatasets.mockResolvedValue([dataset]);
    adminApiMock.getAdaptationEvalDataset.mockResolvedValue({
      ...dataset,
      cases: [caseItem],
    });
    adminApiMock.listAdaptationEvalRuns.mockResolvedValue({
      items: [
        {
          config,
          created_at: now,
          dataset_id: "dataset-1",
          dataset_name: "Adaptation eval set",
          error_message: null,
          finished_at: now,
          id: "run-1",
          latency_ms: 240,
          project_id: "project-1",
          started_at: now,
          status: "success",
          summary_metrics: runDetail.summary_metrics,
        },
      ],
      page: 1,
      page_size: 10,
      total: 1,
    });
    adminApiMock.importAdaptationEvalDataset.mockResolvedValue({
      dataset: { ...dataset, cases: [caseItem] },
      imported_cases: 1,
      warnings: [],
    });
    adminApiMock.createAdaptationEvalRun.mockResolvedValue({
      config,
      created_at: now,
      dataset_id: "dataset-1",
      id: "run-1",
      status: "queued",
    });
    adminApiMock.getAdaptationEvalRun.mockResolvedValue(runDetail);
    adminApiMock.exportAdaptationEvalRun.mockResolvedValue("metric,value\n");
  });

  it("imports a dataset, starts a run, and renders adaptation chain results", async () => {
    render(<AdaptationEvalPage />);

    expect(
      await screen.findByText("Проверка адаптации валидатора"),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Импортировать набор" }),
    );

    await waitFor(() => {
      expect(adminApiMock.importAdaptationEvalDataset).toHaveBeenCalledWith(
        expect.objectContaining({
          dataset_name: "Adaptation eval set",
          project_id: "project-1",
        }),
      );
    });
    expect(
      await screen.findByText("Импортировано кейсов: 1."),
    ).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "Запуск" })[0]);
    fireEvent.click(
      screen.getByRole("button", { name: "Запустить Adaptation Eval" }),
    );

    await waitFor(() => {
      expect(adminApiMock.createAdaptationEvalRun).toHaveBeenCalledWith(
        "dataset-1",
        expect.objectContaining({ retrieval_limit: 5 }),
      );
    });
    expect(await screen.findByText("Пороговые метрики адаптации")).toBeInTheDocument();
    expect(screen.getByText("adapt-auth-positive")).toBeInTheDocument();
    expect(
      screen.getAllByText("Какие роли пользователей должны поддерживаться?")
        .length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("Context validation")).toBeInTheDocument();
    expect(screen.queryByText("Baseline")).not.toBeInTheDocument();
    expect(screen.queryByText("Question delta")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Export" }));
    await waitFor(() => {
      expect(adminApiMock.exportAdaptationEvalRun).toHaveBeenCalledWith(
        "run-1",
        "case_results",
        "csv",
      );
    });
  });
});
