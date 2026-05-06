import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import GraphRunsPage from "@/features/admin/GraphRunsPage";

const adminApiMock = vi.hoisted(() => ({
  getGraphRunDetail: vi.fn(),
  getGraphRuns: vi.fn(),
  getLlmRuntimeSettings: vi.fn(),
  updateLlmRuntimeSettings: vi.fn(),
}));

const mermaidMock = vi.hoisted(() => ({
  initialize: vi.fn(),
  render: vi.fn().mockResolvedValue({
    svg: `
      <svg data-testid="mermaid-svg">
        <g class="node" id="flowchart-evaluate_core_rules-1">
          <rect />
          <text>evaluate_core_rules</text>
        </g>
        <g class="node" id="flowchart-finalize_validation_result-2">
          <rect />
          <text>finalize_validation_result</text>
        </g>
      </svg>
    `,
  }),
}));

vi.mock("mermaid", () => ({
  default: mermaidMock,
}));

vi.mock("@/api/adminApi", async () => {
  const actual = await vi.importActual<typeof import("@/api/adminApi")>(
    "@/api/adminApi",
  );
  return {
    ...actual,
    adminApi: adminApiMock,
  };
});

const runPagePayload = {
  items: [
    {
      actor_name: "Admin",
      actor_user_id: "user-1",
      error_message: null,
      events_count: 2,
      finished_at: "2026-05-05T10:00:01Z",
      graph_key: "validation_graph",
      id: "run-1",
      latency_ms: 100,
      llm_requests_count: 1,
      project_id: "project-1",
      source: "task_validation",
      started_at: "2026-05-05T10:00:00Z",
      status: "success",
      task_id: "task-1",
    },
  ],
  page: 1,
  page_size: 20,
  total: 1,
};

const detailPayload = {
  actor_name: "Admin",
  actor_user_id: "user-1",
  error_message: null,
  events: [],
  final_state_preview: { verdict: "approved" },
  finished_at: "2026-05-05T10:00:01Z",
  graph_key: "validation_graph",
  graph_views: [
    {
      executed_edge_ids: ["evaluate_core_rules->finalize_validation_result"],
      executed_node_ids: ["evaluate_core_rules", "finalize_validation_result"],
      graph_key: "validation_graph",
      mermaid: "flowchart TD\nevaluate_core_rules --> finalize_validation_result",
      nodes: [
        {
          executed: true,
          graph_key: "validation_graph",
          mermaid_id: "evaluate_core_rules",
          node_event_id: "node-1",
          node_name: "evaluate_core_rules",
        },
        {
          executed: true,
          graph_key: "validation_graph",
          mermaid_id: "finalize_validation_result",
          node_event_id: "node-2",
          node_name: "finalize_validation_result",
        },
      ],
      selected_edge_ids: ["evaluate_core_rules->finalize_validation_result"],
    },
  ],
  id: "run-1",
  input_preview: { title: "Task" },
  latency_ms: 100,
  llm_requests: [
    {
      agent_key: "task-validation",
      actor_name: "Admin",
      completion_tokens: 2,
      created_at: "2026-05-05T10:00:00Z",
      error_message: null,
      estimated_cost_usd: null,
      graph_node_name: "evaluate_core_rules",
      graph_run_id: "run-1",
      id: "llm-1",
      latency_ms: 50,
      model: "test-model",
      project_id: "project-1",
      prompt_tokens: 1,
      provider_kind: "openai",
      request_kind: "chat",
      request_messages: null,
      response_text: null,
      status: "success",
      task_id: "task-1",
      total_tokens: 3,
    },
  ],
  node_tree: [
    {
      children: [],
      error_message: null,
      graph_key: "validation_graph",
      id: "node-1",
      input_preview: { title: "Task" },
      latency_ms: 10,
      llm_request_ids: ["llm-1"],
      namespace: "validation_graph",
      node_name: "evaluate_core_rules",
      result_preview: { verdict: "approved" },
      sequence: 1,
      status: "success",
    },
    {
      children: [],
      error_message: null,
      graph_key: "validation_graph",
      id: "node-2",
      input_preview: { verdict: "approved" },
      latency_ms: 8,
      llm_request_ids: [],
      namespace: "validation_graph",
      node_name: "finalize_validation_result",
      result_preview: { response: "done" },
      sequence: 2,
      status: "success",
    },
  ],
  project_id: "project-1",
  source: "task_validation",
  started_at: "2026-05-05T10:00:00Z",
  status: "success",
  task_id: "task-1",
  transitions: [
    {
      condition: "route_after_core_rules",
      condition_input_preview: { verdict: "approved" },
      graph_key: "validation_graph",
      id: "transition-1",
      namespace: "validation_graph",
      reason: "finalize_validation_result",
      selected: ["finalize_validation_result"],
      sequence: 3,
      source_node: "evaluate_core_rules",
      target_nodes: ["finalize_validation_result"],
    },
  ],
};

describe("GraphRunsPage", () => {
  beforeEach(() => {
    adminApiMock.getGraphRuns.mockResolvedValue(runPagePayload);
    adminApiMock.getLlmRuntimeSettings.mockResolvedValue({
      graph_monitoring_enabled: true,
      prompt_log_mode: "full",
    });
    adminApiMock.getGraphRunDetail.mockResolvedValue(detailPayload);
    adminApiMock.updateLlmRuntimeSettings.mockResolvedValue({
      graph_monitoring_enabled: false,
      prompt_log_mode: "full",
    });
    mermaidMock.render.mockClear();
  });

  it("renders graph runs, opens node tree, and expands node input/output", async () => {
    render(<GraphRunsPage />);

    expect(await screen.findByText("Запуски графов")).toBeInTheDocument();
    expect(screen.getByText("Валидация задачи")).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "Валидация задачи" }),
    );

    await waitFor(() => {
      expect(adminApiMock.getGraphRunDetail).toHaveBeenCalledWith("run-1");
    });
    expect(screen.getByText("Выполнение узлов")).toBeInTheDocument();
    expect(screen.getByText("evaluate_core_rules")).toBeInTheDocument();

    await userEvent.click(screen.getAllByRole("button", { name: "Данные" })[0]);

    expect(screen.getByText("Вход узла")).toBeInTheDocument();
    expect(screen.getByText("Выход узла")).toBeInTheDocument();
    expect(screen.getByText("Связанные LLM-вызовы")).toBeInTheDocument();
  });

  it("renders Mermaid graph tab and switches the side panel between SVG node clicks", async () => {
    render(<GraphRunsPage />);

    await userEvent.click(
      await screen.findByRole("button", { name: "Валидация задачи" }),
    );
    await userEvent.click(await screen.findByRole("tab", { name: "Граф" }));

    await waitFor(() => {
      expect(mermaidMock.render).toHaveBeenCalled();
    });
    const node = await screen.findByLabelText(
      "Открыть данные узла evaluate_core_rules",
    );
    await userEvent.click(node);
    await userEvent.click(screen.getByLabelText(/finalize_validation_result$/));
    expect(screen.getByRole("heading", { name: "finalize_validation_result" })).toBeInTheDocument();

    expect(screen.getByText("Узел графа")).toBeInTheDocument();
    expect(screen.getByText("LLM-вызовы узла")).toBeInTheDocument();
    expect(screen.getByText("Выбранные переходы")).toBeInTheDocument();
  });

  it("updates graph monitoring toggle", async () => {
    render(<GraphRunsPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Мониторинг включен" }));

    await waitFor(() => {
      expect(adminApiMock.updateLlmRuntimeSettings).toHaveBeenCalledWith({
        graph_monitoring_enabled: false,
      });
    });
    expect(screen.getByText("Мониторинг выключен")).toBeInTheDocument();
  });
});
