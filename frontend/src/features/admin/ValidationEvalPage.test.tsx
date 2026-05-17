import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ValidationEvalPage from "@/features/admin/ValidationEvalPage";

const adminApiMock = vi.hoisted(() => ({
  createValidationEvalCase: vi.fn(),
  createValidationEvalRun: vi.fn(),
  deleteValidationEvalCase: vi.fn(),
  deleteValidationEvalDataset: vi.fn(),
  deleteValidationEvalRun: vi.fn(),
  exportValidationEvalRun: vi.fn(),
  getValidationEvalDataset: vi.fn(),
  getValidationEvalRun: vi.fn(),
  importValidationEvalDataset: vi.fn(),
  listPromptConfigs: vi.fn(),
  listPromptVersions: vi.fn(),
  listProviders: vi.fn(),
  listValidationEvalDatasets: vi.fn(),
  listValidationEvalRuns: vi.fn(),
  updateValidationEvalCase: vi.fn(),
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

function renderPage() {
  return render(
    <MemoryRouter>
      <ValidationEvalPage />
    </MemoryRouter>,
  );
}

describe("ValidationEvalPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:validation-eval"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    Object.defineProperty(HTMLAnchorElement.prototype, "click", {
      configurable: true,
      value: vi.fn(),
    });

    const now = "2026-05-16T10:00:00.000Z";
    const defaultConfig = {
      run_question_judge: true,
      variants: [
        {
          key: "core_only",
          label: "Core rules",
          provider_config_id: null,
          prompt_version_ids: {},
          validation_node_settings: {
            context_questions: false,
            core_rules: true,
            custom_rules: false,
          },
        },
        {
          key: "core_custom",
          label: "Core + custom rules",
          provider_config_id: null,
          prompt_version_ids: {},
          validation_node_settings: {
            context_questions: false,
            core_rules: true,
            custom_rules: true,
          },
        },
        {
          key: "full",
          label: "Full validation",
          provider_config_id: null,
          prompt_version_ids: {},
          validation_node_settings: {
            context_questions: true,
            core_rules: true,
            custom_rules: true,
          },
        },
      ],
    };
    const dataset = {
      cases_total: 1,
      created_at: now,
      id: "dataset-1",
      last_run_id: "run-1",
      last_run_status: "success",
      name: "Validation eval set",
      project_id: "project-1",
      project_name: "Eval Project",
      updated_at: now,
    };
    const caseItem = {
      attachment_names: ["auth-requirements.md"],
      content: "Нужно описать вход по email и восстановление пароля.",
      custom_rules: [
        {
          applies_to_tags: ["auth"],
          description: "Для задач авторизации нужно явно перечислять роли.",
          title: "Указывать роли",
        },
      ],
      expected_issues: [
        {
          code: "missing_roles",
          message: "Не указаны роли пользователей.",
          rule_title: "Указывать роли",
          severity: "medium",
          source: "custom_rule",
        },
      ],
      expected_context_questions: [
        "Какие ограничения из прошлых задач нужно учесть?",
      ],
      expected_questions: ["Какие роли пользователей должны поддерживаться?"],
      expected_verdict: "needs_rework",
      external_id: "validation-auth-1",
      historical_questions: ["Какие роли должны входить в систему?"],
      id: "case-1",
      metadata: { chapter: "validation-ablation" },
      related_tasks: [],
      tags: ["auth", "security"],
      title: "Авторизация",
      updated_at: now,
    };
    const runDetail = {
      config: defaultConfig,
      created_at: now,
      dataset_id: "dataset-1",
      dataset_name: "Validation eval set",
      error_message: null,
      finished_at: now,
      id: "run-1",
      latency_ms: 240,
      project_id: "project-1",
      started_at: now,
      status: "success",
      summary_metrics: {
        ablation: [
          {
            baseline_variant: "full",
            issue_f1_delta: -0.5,
            context_issue_f1_delta: -1,
            pass_rate_delta: -0.5,
            context_question_f1_delta: -1,
            overall_question_f1_delta: -0.625,
            question_f1_delta: -0.25,
            variant_key: "core_only",
            verdict_accuracy_delta: -0.5,
          },
        ],
        total_results: 2,
        variants: {
          core_only: {
            cases_total: 1,
            confusion_matrix: {
              needs_rework: { approved: 1 },
            },
            custom_rule_coverage: 0,
            estimated_cost_usd: 0.01,
            context_issue_f1: 0,
            context_question_f1: 0,
            context_question_judge: {
              actionability: 0.6,
              novelty: 0.5,
              relevance: 0.7,
              specificity: 0.65,
            },
            issue_f1: 0,
            overall_question_f1: 0.25,
            pass_rate: 0,
            p95_latency_ms: 100,
            question_f1: 0.5,
            question_judge: {
              actionability: 0.7,
              novelty: 0.6,
              relevance: 0.8,
              specificity: 0.75,
            },
            severity_accuracy: null,
            total_tokens: 42,
            verdict_accuracy: 0,
          },
          full: {
            cases_total: 1,
            confusion_matrix: {
              needs_rework: { needs_rework: 1 },
            },
            custom_rule_coverage: 1,
            estimated_cost_usd: 0.02,
            context_issue_f1: 1,
            context_question_f1: 1,
            context_question_judge: {
              actionability: 0.9,
              novelty: 0.88,
              relevance: 0.92,
              specificity: 0.91,
            },
            issue_f1: 1,
            overall_question_f1: 1,
            pass_rate: 1,
            p95_latency_ms: 140,
            question_f1: 1,
            question_judge: {
              actionability: 0.95,
              novelty: 0.9,
              relevance: 0.96,
              specificity: 0.94,
            },
            severity_accuracy: 1,
            total_tokens: 84,
            verdict_accuracy: 1,
          },
        },
      },
      case_results: [
        {
          actual_result: {
            issues: [
              {
                code: "missing_roles",
                message: "Не указаны роли пользователей.",
                severity: "medium",
              },
            ],
            context_questions: [
              "Какие ограничения из прошлых задач нужно учесть?",
            ],
            questions: ["Какие роли пользователей должны поддерживаться?"],
            verdict: "needs_rework",
          },
          case_external_id: "validation-auth-1",
          case_id: "case-1",
          created_at: now,
          diffs: {
            extra_questions: [],
            extra_context_questions: [],
            false_negative_issues: [],
            false_positive_issues: [],
            missing_context_questions: [],
            missing_questions: [],
          },
          error_message: null,
          expected_result: {
            issues: [
              {
                code: "missing_roles",
                message: "Не указаны роли пользователей.",
                severity: "medium",
              },
            ],
            context_questions: [
              "Какие ограничения из прошлых задач нужно учесть?",
            ],
            questions: ["Какие роли пользователей должны поддерживаться?"],
            verdict: "needs_rework",
          },
          graph_run_id: "graph-run-full",
          id: "result-1",
          judge_graph_run_id: "judge-run-full",
          judge_payload: {
            context_questions: {
              actionability: 0.9,
              novelty: 0.88,
              relevance: 0.92,
              specificity: 0.91,
            },
            final_questions: {
              actionability: 0.95,
              novelty: 0.9,
              relevance: 0.96,
              specificity: 0.94,
            },
          },
          latency_ms: 140,
          metrics: {
            actual_verdict: "needs_rework",
            expected_verdict: "needs_rework",
            context_question_f1: 1,
            context_question_precision: 1,
            context_question_recall: 1,
            issue_f1: 1,
            issue_precision: 1,
            issue_recall: 1,
            overall_question_f1: 1,
            question_duplicates: 0,
            question_f1: 1,
            question_precision: 1,
            question_recall: 1,
            verdict_match: true,
          },
          status: "passed",
          variant_key: "full",
          variant_label: "Full validation",
        },
        {
          actual_result: {
            issues: [
              {
                code: "extra_scope",
                message: "Лишняя проблема про scope.",
                severity: "low",
              },
            ],
            questions: ["Лишний вопрос про интеграции?"],
            context_questions: ["Лишний контекстный вопрос?"],
            verdict: "approved",
          },
          case_external_id: "validation-payment-1",
          case_id: "case-2",
          created_at: now,
          diffs: {
            extra_questions: ["Лишний вопрос про интеграции?"],
            extra_context_questions: ["Лишний контекстный вопрос?"],
            false_negative_issues: [
              {
                code: "missing_roles",
                message: "Не указаны роли пользователей.",
                severity: "medium",
              },
            ],
            false_positive_issues: [
              {
                code: "extra_scope",
                message: "Лишняя проблема про scope.",
                severity: "low",
              },
            ],
            missing_questions: [
              "Какие роли пользователей должны поддерживаться?",
            ],
            missing_context_questions: [
              "Какие ограничения из прошлых задач нужно учесть?",
            ],
          },
          error_message: null,
          expected_result: {
            issues: [
              {
                code: "missing_roles",
                message: "Не указаны роли пользователей.",
                severity: "medium",
              },
            ],
            context_questions: [
              "Какие ограничения из прошлых задач нужно учесть?",
            ],
            questions: ["Какие роли пользователей должны поддерживаться?"],
            verdict: "needs_rework",
          },
          graph_run_id: "graph-run-core",
          id: "result-2",
          judge_graph_run_id: "judge-run-core",
          judge_payload: {
            actionability: 0.7,
            novelty: 0.6,
            relevance: 0.8,
            specificity: 0.75,
          },
          latency_ms: 100,
          metrics: {
            actual_verdict: "approved",
            expected_verdict: "needs_rework",
            context_question_f1: 0,
            issue_f1: 0,
            issue_precision: 0,
            issue_recall: 0,
            overall_question_f1: 0.25,
            question_duplicates: 1,
            question_f1: 0.5,
            question_precision: 0.5,
            question_recall: 0.5,
            verdict_match: false,
          },
          status: "failed",
          variant_key: "core_only",
          variant_label: "Core rules",
        },
      ],
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
    adminApiMock.listValidationEvalDatasets.mockResolvedValue([dataset]);
    adminApiMock.getValidationEvalDataset.mockResolvedValue({
      ...dataset,
      cases: [caseItem],
    });
    adminApiMock.importValidationEvalDataset.mockResolvedValue({
      dataset: { ...dataset, cases: [caseItem] },
      imported_cases: 1,
      warnings: [],
    });
    adminApiMock.createValidationEvalRun.mockResolvedValue({
      config: defaultConfig,
      created_at: now,
      dataset_id: "dataset-1",
      id: "run-1",
      status: "queued",
    });
    adminApiMock.listValidationEvalRuns.mockResolvedValue({
      items: [
        {
          config: defaultConfig,
          created_at: now,
          dataset_id: "dataset-1",
          dataset_name: "Validation eval set",
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
    adminApiMock.getValidationEvalRun.mockResolvedValue(runDetail);
    adminApiMock.exportValidationEvalRun.mockResolvedValue(
      "case_external_id\n",
    );
    adminApiMock.deleteValidationEvalRun.mockResolvedValue(undefined);
    adminApiMock.deleteValidationEvalDataset.mockResolvedValue(undefined);
    adminApiMock.createValidationEvalCase.mockResolvedValue({
      ...caseItem,
      external_id: "manual-case-1",
      id: "case-2",
      title: "Ручной кейс",
    });
    adminApiMock.updateValidationEvalCase.mockResolvedValue({
      ...caseItem,
      title: "Авторизация обновлена",
    });
    adminApiMock.deleteValidationEvalCase.mockResolvedValue(undefined);
    adminApiMock.listProviders.mockResolvedValue([
      {
        base_url: "https://api.openai.com/v1",
        created_at: now,
        enabled: true,
        id: "provider-1",
        input_cost_per_1k_tokens: "0.001",
        is_default: true,
        masked_secret: "***",
        model: "gpt-4o-mini",
        name: "OpenAI mini",
        output_cost_per_1k_tokens: "0.002",
        provider_kind: "openai",
        secret_configured: true,
        temperature: 0.2,
        updated_at: now,
        used_by_agents: [],
        vision_detail: "default",
        vision_enabled: true,
        vision_message_order: "text_first",
        vision_system_prompt_mode: "system_role",
      },
    ]);
    adminApiMock.listPromptConfigs.mockResolvedValue([
      {
        agent_key: "task-validation",
        aliases: [],
        default_description: "Core validation",
        default_system_prompt: "Validate task",
        effective_description: "Core validation",
        effective_system_prompt: "Validate task",
        name: "Task validation core",
        override_description: null,
        override_enabled: false,
        override_system_prompt: null,
        prompt_key: "task-validation-core",
        revision: 1,
        updated_at: now,
      },
    ]);
    adminApiMock.listPromptVersions.mockResolvedValue([
      {
        agent_key: "task-validation",
        created_at: now,
        description: "Core validation",
        enabled: true,
        id: "prompt-version-1",
        prompt_key: "task-validation-core",
        revision: 1,
        system_prompt: "Validate task",
      },
    ]);
  });

  it("imports a JSON dataset and starts a Validation Eval run", async () => {
    renderPage();

    expect(
      await screen.findByText("Эксперименты валидатора"),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Импортировать набор" }),
    );

    await waitFor(() => {
      expect(adminApiMock.importValidationEvalDataset).toHaveBeenCalledWith({
        content: expect.stringContaining("Авторизация"),
        dataset_name: null,
        format: "json",
        project_id: "project-1",
      });
    });
    expect(
      await screen.findByText(/Импортировано кейсов: 1/),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Запуск" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Запустить Validation Eval" }),
    );

    await waitFor(() => {
      expect(adminApiMock.createValidationEvalRun).toHaveBeenCalledWith(
        "dataset-1",
        expect.objectContaining({
          run_question_judge: true,
          variants: expect.arrayContaining([
            expect.objectContaining({ key: "core_only" }),
            expect.objectContaining({ key: "core_custom" }),
            expect.objectContaining({ key: "full" }),
          ]),
        }),
      );
    });
    expect(await screen.findByText("validation-auth-1")).toBeInTheDocument();
  });

  it("creates, edits, and deletes a manual eval case with Russian text", async () => {
    renderPage();

    await screen.findByText("Эксперименты валидатора");
    fireEvent.click(screen.getByRole("button", { name: "Кейсы" }));
    expect(await screen.findByText("validation-auth-1")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Редактировать" }));
    fireEvent.change(screen.getByLabelText("Название"), {
      target: { value: "Авторизация обновлена" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить кейс" }));

    await waitFor(() => {
      expect(adminApiMock.updateValidationEvalCase).toHaveBeenCalledWith(
        "dataset-1",
        "case-1",
        expect.objectContaining({
          title: "Авторизация обновлена",
        }),
      );
    });

    fireEvent.change(screen.getByLabelText("External ID"), {
      target: { value: "manual-case-1" },
    });
    fireEvent.change(screen.getByLabelText("Название"), {
      target: { value: "Ручной кейс" },
    });
    fireEvent.change(screen.getByLabelText("Текст задачи"), {
      target: { value: "Проверить, что русская кодировка не ломается." },
    });
    fireEvent.change(screen.getByLabelText("Expected issues JSON"), {
      target: {
        value:
          '[{"code":"encoding","severity":"low","message":"Проверка русской кодировки."}]',
      },
    });
    fireEvent.change(screen.getByLabelText("Expected context questions"), {
      target: { value: "Какие исторические вопросы нужно учесть?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Создать кейс" }));

    await waitFor(() => {
      expect(adminApiMock.createValidationEvalCase).toHaveBeenCalledWith(
        "dataset-1",
        expect.objectContaining({
          content: "Проверить, что русская кодировка не ломается.",
          expected_issues: [
            {
              code: "encoding",
              message: "Проверка русской кодировки.",
              severity: "low",
            },
          ],
          expected_context_questions: [
            "Какие исторические вопросы нужно учесть?",
          ],
          external_id: "manual-case-1",
          title: "Ручной кейс",
        }),
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "Удалить" }));
    expect(
      await screen.findByRole("heading", { name: "Удалить кейс?" }),
    ).toBeInTheDocument();
    const deleteButtons = screen.getAllByRole("button", { name: "Удалить" });
    fireEvent.click(deleteButtons[deleteButtons.length - 1]);

    await waitFor(() => {
      expect(adminApiMock.deleteValidationEvalCase).toHaveBeenCalledWith(
        "dataset-1",
        "case-1",
      );
    });
  });

  it("renders results, filters failed cases, and exports every artifact", async () => {
    renderPage();

    await screen.findByText("Эксперименты валидатора");
    fireEvent.click(screen.getByRole("button", { name: "Запуск" }));
    expect(await screen.findByText("История запусков")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Открыть" }));

    expect(await screen.findByText("Метрики по variants")).toBeInTheDocument();
    expect(screen.getByText("Дельты относительно full")).toBeInTheDocument();
    expect(screen.getByText("Approved / needs_rework")).toBeInTheDocument();
    expect(screen.getByText("validation-payment-1")).toBeInTheDocument();
    expect(
      screen.getAllByText(/Лишняя проблема про scope/).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByText("Какие роли пользователей должны поддерживаться?"),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Status"), {
      target: { value: "failed" },
    });
    expect(screen.queryByText("validation-auth-1")).not.toBeInTheDocument();
    expect(screen.getByText("validation-payment-1")).toBeInTheDocument();

    for (const artifact of [
      "case_results",
      "metrics",
      "confusion_matrix",
      "ablation",
      "errors",
    ]) {
      fireEvent.change(screen.getByLabelText("Export artifact"), {
        target: { value: artifact },
      });
      fireEvent.change(screen.getByLabelText("Export format"), {
        target: { value: "csv" },
      });
      fireEvent.click(screen.getByRole("button", { name: "Export" }));
      await waitFor(() => {
        expect(adminApiMock.exportValidationEvalRun).toHaveBeenCalledWith(
          "run-1",
          artifact,
          "csv",
        );
      });
    }

    fireEvent.change(screen.getByLabelText("Export format"), {
      target: { value: "json" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Export" }));
    await waitFor(() => {
      expect(adminApiMock.exportValidationEvalRun).toHaveBeenCalledWith(
        "run-1",
        "errors",
        "json",
      );
    });
  });
});
