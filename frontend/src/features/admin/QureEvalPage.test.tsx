import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

import QureEvalPage from "@/features/admin/QureEvalPage";

const adminApiMock = vi.hoisted(() => ({
  createQureEvalRun: vi.fn(),
  deleteQureEvalRun: vi.fn(),
  exportQureEvalRun: vi.fn(),
  getQureEvalRun: vi.fn(),
  listQureEvalRuns: vi.fn(),
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

function runDetail() {
  const now = "2026-05-20T10:00:00.000Z";
  return {
    case_results: [
      {
        actual_result: {
          issues: [
            {
              code: "ambiguous_language",
              message: "Potential weak wording: fast",
            },
          ],
          verdict: "needs_rework",
        },
        created_at: now,
        defect: "defect",
        error_message: null,
        expected_verdict: "needs_rework",
        graph_run_id: "graph-1",
        id: "case-1",
        judge_graph_run_id: "judge-1",
        judge_payload: {
          match: true,
          passed: true,
          rationale: "Validator caught the QuRE weak-word defect.",
          score: 1,
          verdict_match: true,
          weak_word_match: true,
        },
        metrics: { judge_passed: true, weak_word_tp: 1 },
        requirement: "The system shall respond fast.",
        row_index: 1,
        run_id: "run-1",
        source_id: "1",
        status: "passed",
        latency_ms: 100,
        weak_word: "fast",
      },
    ],
    created_at: now,
    error_message: null,
    file_sha256: "abc",
    filename: "QuRE.csv",
    finished_at: now,
    id: "run-1",
    latency_ms: 1000,
    project_id: "project-1",
    project_name: "Eval Project",
    row_limit: 4,
    selected_rows: 4,
    selection_strategy: "stratified_by_defect_then_weak_word_v1",
    started_at: now,
    status: "success",
    summary_metrics: {
      judge_errors: 0,
      judge_pass_rate: 1,
      verdict_accuracy: 0.75,
      verdict_f1: 0.8,
      weak_word_f1: 0.5,
    },
    total_rows: 2187,
  };
}

function renderPage() {
  return render(<QureEvalPage />);
}

describe("QureEvalPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:qure-eval"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    Object.defineProperty(HTMLAnchorElement.prototype, "click", {
      configurable: true,
      value: vi.fn(),
    });

    projectsApiMock.list.mockResolvedValue([
      {
        created_at: "2026-05-20T10:00:00.000Z",
        created_by: "user-1",
        description: null,
        id: "project-1",
        name: "Eval Project",
        updated_at: "2026-05-20T10:00:00.000Z",
        validation_node_settings: {
          context_questions: false,
          core_rules: true,
          custom_rules: false,
        },
      },
    ]);
    adminApiMock.listQureEvalRuns.mockResolvedValue({
      items: [runDetail()],
      page: 1,
      page_size: 20,
      total: 1,
    });
    adminApiMock.getQureEvalRun.mockResolvedValue(runDetail());
    adminApiMock.createQureEvalRun.mockResolvedValue({
      created_at: "2026-05-20T10:00:00.000Z",
      id: "run-2",
      project_id: "project-1",
      row_limit: 4,
      selected_rows: 4,
      selection_strategy: "stratified_by_defect_then_weak_word_v1",
      status: "queued",
      total_rows: 2187,
    });
    adminApiMock.exportQureEvalRun.mockResolvedValue("id,weak_word\n1,fast\n");
  });

  it("shows existing QuRE Eval results", async () => {
    renderPage();

    expect(await screen.findByText("QuRE Eval")).toBeInTheDocument();
    expect(screen.getByText("Judge pass rate")).toBeInTheDocument();
    expect(screen.getByText("Weak-word F1")).toBeInTheDocument();
    expect(screen.getByText("0.5000")).toBeInTheDocument();
    expect(screen.getByText("fast")).toBeInTheDocument();
    expect(
      screen.getByText("Validator caught the QuRE weak-word defect."),
    ).toBeInTheDocument();
  });

  it("shows validator and judge payload details for a case", async () => {
    renderPage();

    fireEvent.click(await screen.findByText("Ответы"));

    expect(screen.getByText("Ответ валидатора")).toBeInTheDocument();
    expect(screen.getByText("Ответ judge")).toBeInTheDocument();
    expect(screen.getByText(/ambiguous_language/)).toBeInTheDocument();
    expect(
      screen.getAllByText(/Validator caught the QuRE weak-word defect/).length,
    ).toBeGreaterThan(0);
  });

  it("requires file, project, and limit before creating a run", async () => {
    renderPage();

    const submit = await screen.findByRole("button", { name: "Запустить" });
    expect(submit).toBeDisabled();

    const file = new File(["id,requirement,defect,weak_word\n"], "QuRE.csv", {
      type: "text/csv",
    });
    fireEvent.change(screen.getByLabelText("Исходный QuRE.csv"), {
      target: { files: [file] },
    });
    fireEvent.change(screen.getByLabelText("Лимит строк"), {
      target: { value: "4" },
    });
    fireEvent.click(submit);

    await waitFor(() => {
      expect(adminApiMock.createQureEvalRun).toHaveBeenCalledWith(
        file,
        "project-1",
        4,
      );
    });
  });
});
