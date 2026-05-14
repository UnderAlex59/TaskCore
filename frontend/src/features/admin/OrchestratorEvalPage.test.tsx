import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import OrchestratorEvalPage from "@/features/admin/OrchestratorEvalPage";

const adminApiMock = vi.hoisted(() => ({
  createOrchestratorEvalRun: vi.fn(),
  deleteOrchestratorEvalRun: vi.fn(),
  exportOrchestratorEvalRun: vi.fn(),
  getOrchestratorEvalDataset: vi.fn(),
  getOrchestratorEvalRun: vi.fn(),
  importOrchestratorEvalDataset: vi.fn(),
  listOrchestratorEvalDatasets: vi.fn(),
  listOrchestratorEvalRuns: vi.fn(),
  runOrchestratorEvalPlayground: vi.fn(),
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

function renderPage() {
  render(
    <MemoryRouter>
      <OrchestratorEvalPage />
    </MemoryRouter>,
  );
}

describe("OrchestratorEvalPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:test"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    HTMLAnchorElement.prototype.click = vi.fn();
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
    tasksApiMock.list.mockResolvedValue([
      {
        id: "task-1",
        project_id: "project-1",
        title: "Авторизация",
        content: "Описание задачи с корректной русской кодировкой.",
        tags: [],
        status: "draft",
        created_by: "admin-1",
        analyst_id: "admin-1",
        reviewer_analyst_id: null,
        developer_id: null,
        tester_id: null,
        reviewer_approved_at: null,
        validation_result: null,
        attachments: [],
        indexed_at: null,
        embeddings_stale: false,
        requires_revalidation: false,
        created_at: now,
        updated_at: now,
      },
    ]);
    adminApiMock.listOrchestratorEvalDatasets.mockResolvedValue([
      {
        id: "dataset-1",
        project_id: "project-1",
        project_name: "Eval Project",
        name: "Orchestrator eval set",
        cases_total: 2,
        last_run_id: "run-1",
        last_run_status: "success",
        created_at: now,
        updated_at: now,
      },
    ]);
    adminApiMock.getOrchestratorEvalDataset.mockResolvedValue({
      id: "dataset-1",
      project_id: "project-1",
      project_name: "Eval Project",
      name: "Orchestrator eval set",
      cases_total: 2,
      last_run_id: "run-1",
      last_run_status: "success",
      created_at: now,
      updated_at: now,
      cases: [
        {
          id: "case-1",
          external_id: "route-qa-1",
          input: {
            project_id: "project-1",
            task_id: null,
            task_title: "Авторизация",
            task_status: "draft",
            task_content: "Описание задачи с корректной русской кодировкой.",
            validation_result: null,
            message_content: "@qa Какие требования?",
            requested_agent: null,
          },
          expected_route: {
            ai_response_required: true,
            target_agent_key: "qa",
          },
          updated_at: now,
        },
      ],
    });
    adminApiMock.runOrchestratorEvalPlayground.mockResolvedValue({
      status: "passed",
      input: {
        project_id: "project-1",
        task_id: null,
        task_title: "Авторизация",
        task_status: "draft",
        task_content: "Описание задачи с корректной русской кодировкой.",
        validation_result: null,
        message_content: "@qa Какие требования?",
        requested_agent: null,
      },
      expected_route: {
        ai_response_required: true,
        target_agent_key: "qa",
        message_type: "question",
        routing_mode: "auto",
      },
      actual_route: {
        ai_response_required: true,
        target_agent_key: "qa",
        message_type: "question",
        routing_mode: "auto",
        routing_reason: "auto_agent:qa",
      },
      metrics: {
        passed: true,
        field_matches: {
          ai_response_required: true,
          target_agent_key: true,
          message_type: true,
          routing_mode: true,
        },
      },
      graph_run_id: "graph-run-1",
      latency_ms: 42,
      error_message: null,
    });
    adminApiMock.importOrchestratorEvalDataset.mockResolvedValue({
      dataset: {
        id: "dataset-1",
        project_id: "project-1",
        project_name: "Eval Project",
        name: "Orchestrator eval set",
        cases_total: 2,
        last_run_id: "run-1",
        last_run_status: "success",
        created_at: now,
        updated_at: now,
        cases: [],
      },
      imported_cases: 2,
      warnings: [],
    });
    adminApiMock.createOrchestratorEvalRun.mockResolvedValue({
      id: "run-1",
      dataset_id: "dataset-1",
      status: "queued",
      config: { compare_reason: true },
      created_at: now,
    });
    adminApiMock.listOrchestratorEvalRuns.mockResolvedValue({
      page: 1,
      page_size: 10,
      total: 1,
      items: [
        {
          id: "run-1",
          dataset_id: "dataset-1",
          dataset_name: "Orchestrator eval set",
          project_id: "project-1",
          status: "success",
          config: { compare_reason: true },
          summary_metrics: {
            total: 2,
            passed: 1,
            failed: 1,
            errors: 0,
            pass_rate: 0.5,
          },
          started_at: now,
          finished_at: now,
          latency_ms: 100,
          error_message: null,
          created_at: now,
        },
      ],
    });
    adminApiMock.getOrchestratorEvalRun.mockResolvedValue({
      id: "run-1",
      dataset_id: "dataset-1",
      dataset_name: "Orchestrator eval set",
      project_id: "project-1",
      status: "success",
      config: { compare_reason: true },
      summary_metrics: {
        total: 2,
        passed: 1,
        failed: 1,
        errors: 0,
        pass_rate: 0.5,
        total_tokens: 12,
      },
      started_at: now,
      finished_at: now,
      latency_ms: 100,
      error_message: null,
      created_at: now,
      case_results: [
        {
          id: "result-1",
          case_id: "case-1",
          case_external_id: "route-qa-pass",
          status: "passed",
          input: {
            project_id: "project-1",
            task_id: null,
            task_title: "Авторизация",
            task_status: "draft",
            task_content: "Описание задачи с корректной русской кодировкой.",
            validation_result: null,
            message_content: "@qa Какие требования?",
            requested_agent: null,
          },
          expected_route: { target_agent_key: "qa", routing_mode: "forced" },
          actual_route: {
            ai_response_required: true,
            target_agent_key: "qa",
            message_type: "general",
            routing_mode: "forced",
            routing_reason: "forced_agent",
          },
          metrics: {
            passed: true,
            field_matches: { target_agent_key: true, routing_mode: true },
          },
          graph_run_id: "graph-run-1",
          latency_ms: 50,
          error_message: null,
          created_at: now,
        },
        {
          id: "result-2",
          case_id: "case-2",
          case_external_id: "route-qa-fail",
          status: "failed",
          input: {
            project_id: "project-1",
            task_id: null,
            task_title: "Авторизация",
            task_status: "draft",
            task_content: "Описание задачи с корректной русской кодировкой.",
            validation_result: null,
            message_content: "@qa Какие требования?",
            requested_agent: null,
          },
          expected_route: { target_agent_key: "change-tracker" },
          actual_route: {
            ai_response_required: true,
            target_agent_key: "qa",
            message_type: "general",
            routing_mode: "forced",
            routing_reason: "forced_agent",
          },
          metrics: {
            passed: false,
            field_matches: { target_agent_key: false },
          },
          graph_run_id: "graph-run-2",
          latency_ms: 60,
          error_message: null,
          created_at: now,
        },
      ],
    });
    adminApiMock.exportOrchestratorEvalRun.mockResolvedValue(
      "case_external_id\nroute-qa-pass\n",
    );
    adminApiMock.deleteOrchestratorEvalRun.mockResolvedValue(undefined);
  });

  it("runs playground dry-run and renders route comparison as UI", async () => {
    renderPage();

    expect(
      await screen.findByText("Тест маршрутизации оркестратора"),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Запустить dry-run" }));

    await waitFor(() => {
      expect(adminApiMock.runOrchestratorEvalPlayground).toHaveBeenCalledWith(
        expect.objectContaining({
          expected_route: expect.objectContaining({ target_agent_key: "qa" }),
        }),
      );
    });
    expect(await screen.findByText("Dry-run result")).toBeInTheDocument();
    expect(screen.getAllByText("AI-ответ").length).toBeGreaterThan(0);
    expect(screen.getAllByText("qa").length).toBeGreaterThan(0);
    expect(screen.queryByText(/"actual_route"/)).not.toBeInTheDocument();
  });

  it("imports a dataset, starts a run, filters failed cases, and exports CSV", async () => {
    renderPage();

    await screen.findByText("Тест маршрутизации оркестратора");
    fireEvent.click(screen.getByRole("button", { name: "Импорт" }));
    fireEvent.click(screen.getByRole("button", { name: "Импортировать набор" }));

    await waitFor(() => {
      expect(adminApiMock.importOrchestratorEvalDataset).toHaveBeenCalledWith({
        format: "json",
        content: expect.stringContaining("Orchestrator eval set"),
      });
    });
    expect(await screen.findByText(/Импортировано кейсов/)).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Запустить Orchestrator Eval" }),
    );
    await waitFor(() => {
      expect(adminApiMock.createOrchestratorEvalRun).toHaveBeenCalledWith(
        "dataset-1",
        { compare_reason: true },
      );
    });

    expect(await screen.findByText("route-qa-pass")).toBeInTheDocument();
    expect(screen.getByText("route-qa-fail")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Status"), {
      target: { value: "failed" },
    });
    expect(screen.queryByText("route-qa-pass")).not.toBeInTheDocument();
    expect(screen.getByText("route-qa-fail")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    await waitFor(() => {
      expect(adminApiMock.exportOrchestratorEvalRun).toHaveBeenCalledWith(
        "run-1",
        "csv",
      );
    });
  });
});
