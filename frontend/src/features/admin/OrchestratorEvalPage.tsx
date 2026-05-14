import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import {
  adminApi,
  type OrchestratorEvalCaseResultRead,
  type OrchestratorEvalDatasetDetailRead,
  type OrchestratorEvalDatasetRead,
  type OrchestratorEvalExpectedRoute,
  type OrchestratorEvalImportFormat,
  type OrchestratorEvalInput,
  type OrchestratorEvalPlaygroundResultRead,
  type OrchestratorEvalRunConfig,
  type OrchestratorEvalRunListItemRead,
  type OrchestratorEvalRunPageRead,
  type OrchestratorEvalRunRead,
  type OrchestratorEvalRunStatus,
} from "@/api/adminApi";
import { projectsApi, type ProjectRead } from "@/api/projectsApi";
import { tasksApi, type TaskRead } from "@/api/tasksApi";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { LoadingSpinner } from "@/shared/components/LoadingSpinner";
import { getApiErrorMessage } from "@/shared/lib/apiError";
import { formatDateTimeFull } from "@/shared/lib/locale";

type OrchestratorEvalTab =
  | "playground"
  | "import"
  | "datasets"
  | "run"
  | "results";
type RunStatusFilter = OrchestratorEvalRunStatus | "all";
type CaseStatusFilter = "all" | "passed" | "failed" | "error";

const TABS: Array<{ key: OrchestratorEvalTab; label: string }> = [
  { key: "playground", label: "Playground" },
  { key: "import", label: "Импорт" },
  { key: "datasets", label: "Наборы" },
  { key: "run", label: "Запуск" },
  { key: "results", label: "Результаты" },
];

const RUN_HISTORY_PAGE_SIZE = 10;

const DEFAULT_CONFIG: OrchestratorEvalRunConfig = {
  compare_reason: true,
};

const EMPTY_INPUT: OrchestratorEvalInput = {
  project_id: "",
  task_id: null,
  task_title: "Тестовая задача",
  task_status: "draft",
  task_content: "",
  validation_result: null,
  message_content: "Какие требования нужно уточнить?",
  requested_agent: null,
};

const JSON_TEMPLATE = `{
  "dataset_name": "Orchestrator eval set",
  "project_id": "project-id",
  "cases": [
    {
      "external_id": "route-qa-1",
      "input": {
        "project_id": "project-id",
        "task_id": null,
        "task_title": "Авторизация",
        "task_status": "draft",
        "task_content": "Нужно описать авторизацию пользователей.",
        "validation_result": null,
        "message_content": "Какие требования к авторизации?",
        "requested_agent": null
      },
      "expected_route": {
        "ai_response_required": true,
        "target_agent_key": "qa",
        "message_type": "question",
        "routing_mode": "auto"
      }
    }
  ]
}`;

const CSV_TEMPLATE = `case_external_id,task_title,task_status,task_content,message_content,requested_agent,expected_ai_response_required,expected_target_agent_key,expected_message_type,expected_routing_mode,expected_reason_contains
route-qa-1,Авторизация,draft,Нужно описать авторизацию пользователей.,Какие требования к авторизации?,,true,qa,question,auto,`;

function statusLabel(status: string | null | undefined) {
  switch (status) {
    case "queued":
      return "В очереди";
    case "running":
      return "Выполняется";
    case "success":
      return "Готово";
    case "error":
      return "Ошибка";
    case "passed":
      return "Passed";
    case "failed":
      return "Failed";
    default:
      return "н/д";
  }
}

function metricValue(value: unknown) {
  if (typeof value === "number") {
    if (value > 0 && value <= 1) {
      return `${Math.round(value * 1000) / 10}%`;
    }
    return value.toLocaleString("ru-RU");
  }
  if (value === null || value === undefined || value === "") {
    return "н/д";
  }
  return String(value);
}

function formatMs(value: number | null | undefined) {
  return value === null || value === undefined
    ? "н/д"
    : `${value.toLocaleString("ru-RU")} мс`;
}

function asRecord(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}

function normalizedText(value: unknown) {
  return String(value ?? "").toLocaleLowerCase("ru-RU");
}

function shortText(value: unknown, maxLength = 220) {
  const text = String(value ?? "")
    .replace(/\s+/g, " ")
    .trim();
  if (!text) {
    return "н/д";
  }
  return text.length > maxLength ? `${text.slice(0, maxLength).trim()}...` : text;
}

function downloadText(filename: string, content: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function buildExpectedRoute(
  aiResponse: string,
  targetAgent: string,
  messageType: string,
  routingMode: string,
  reasonContains: string,
): OrchestratorEvalExpectedRoute {
  return {
    ...(aiResponse ? { ai_response_required: aiResponse === "true" } : {}),
    ...(targetAgent.trim() ? { target_agent_key: targetAgent.trim() } : {}),
    ...(messageType ? { message_type: messageType as never } : {}),
    ...(routingMode ? { routing_mode: routingMode as never } : {}),
    ...(reasonContains.trim()
      ? { reason_contains: reasonContains.trim() }
      : {}),
  };
}

function fillInputFromTask(task: TaskRead): OrchestratorEvalInput {
  return {
    project_id: task.project_id,
    task_id: task.id,
    task_title: task.title,
    task_status: task.status,
    task_content: task.content,
    validation_result: task.validation_result as Record<string, unknown> | null,
    message_content: "Какие требования нужно уточнить?",
    requested_agent: null,
  };
}

export default function OrchestratorEvalPage() {
  const [activeTab, setActiveTab] =
    useState<OrchestratorEvalTab>("playground");
  const [projects, setProjects] = useState<ProjectRead[]>([]);
  const [tasks, setTasks] = useState<TaskRead[]>([]);
  const [datasets, setDatasets] = useState<OrchestratorEvalDatasetRead[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [selectedTaskId, setSelectedTaskId] = useState("");
  const [selectedDatasetId, setSelectedDatasetId] = useState("");
  const [datasetDetail, setDatasetDetail] =
    useState<OrchestratorEvalDatasetDetailRead | null>(null);
  const [runHistory, setRunHistory] =
    useState<OrchestratorEvalRunPageRead | null>(null);
  const [activeRun, setActiveRun] = useState<OrchestratorEvalRunRead | null>(
    null,
  );
  const [runPendingDeletion, setRunPendingDeletion] =
    useState<OrchestratorEvalRunListItemRead | null>(null);
  const [runHistoryPage, setRunHistoryPage] = useState(1);
  const [runHistoryStatus, setRunHistoryStatus] =
    useState<RunStatusFilter>("all");
  const [caseStatusFilter, setCaseStatusFilter] =
    useState<CaseStatusFilter>("all");
  const [caseAgentFilter, setCaseAgentFilter] = useState("all");
  const [caseModeFilter, setCaseModeFilter] = useState("all");
  const [caseSearch, setCaseSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [runHistoryLoading, setRunHistoryLoading] = useState(false);
  const [deletingRunId, setDeletingRunId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [config, setConfig] = useState<OrchestratorEvalRunConfig>(DEFAULT_CONFIG);
  const [playgroundInput, setPlaygroundInput] =
    useState<OrchestratorEvalInput>(EMPTY_INPUT);
  const [expectedAiResponse, setExpectedAiResponse] = useState("true");
  const [expectedTargetAgent, setExpectedTargetAgent] = useState("qa");
  const [expectedMessageType, setExpectedMessageType] = useState("question");
  const [expectedRoutingMode, setExpectedRoutingMode] = useState("auto");
  const [expectedReasonContains, setExpectedReasonContains] = useState("");
  const [playgroundResult, setPlaygroundResult] =
    useState<OrchestratorEvalPlaygroundResultRead | null>(null);
  const [importFormat, setImportFormat] =
    useState<OrchestratorEvalImportFormat>("json");
  const [importName, setImportName] = useState("Orchestrator eval set");
  const [importContent, setImportContent] = useState(JSON_TEMPLATE);

  async function loadBootstrap() {
    try {
      setLoading(true);
      setError(null);
      const [projectList, datasetList] = await Promise.all([
        projectsApi.list(),
        adminApi.listOrchestratorEvalDatasets(),
      ]);
      setProjects(projectList);
      setDatasets(datasetList);
      const initialProjectId = selectedProjectId || projectList[0]?.id || "";
      setSelectedProjectId(initialProjectId);
      setSelectedDatasetId((current) => current || datasetList[0]?.id || "");
      setPlaygroundInput((current) => ({
        ...current,
        project_id: current.project_id || initialProjectId,
      }));
    } catch (caught) {
      setError(
        getApiErrorMessage(caught, "Не удалось загрузить Orchestrator Eval."),
      );
    } finally {
      setLoading(false);
    }
  }

  async function loadTasks(projectId: string) {
    if (!projectId) {
      setTasks([]);
      return;
    }
    try {
      setTasks(await tasksApi.list(projectId));
    } catch {
      setTasks([]);
    }
  }

  async function loadDataset(datasetId: string) {
    if (!datasetId) {
      setDatasetDetail(null);
      return;
    }
    try {
      setError(null);
      setDatasetDetail(await adminApi.getOrchestratorEvalDataset(datasetId));
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось загрузить eval-набор."));
    }
  }

  async function loadRunHistory(
    datasetId: string,
    page = runHistoryPage,
    status = runHistoryStatus,
  ) {
    if (!datasetId) {
      setRunHistory(null);
      return;
    }
    try {
      setRunHistoryLoading(true);
      setError(null);
      setRunHistory(
        await adminApi.listOrchestratorEvalRuns(datasetId, {
          page,
          size: RUN_HISTORY_PAGE_SIZE,
          ...(status !== "all" ? { status } : {}),
        }),
      );
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось загрузить историю."));
    } finally {
      setRunHistoryLoading(false);
    }
  }

  useEffect(() => {
    void loadBootstrap();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    void loadTasks(selectedProjectId);
    setPlaygroundInput((current) => ({
      ...current,
      project_id: selectedProjectId,
      task_id: current.project_id === selectedProjectId ? current.task_id : null,
    }));
  }, [selectedProjectId]);

  useEffect(() => {
    const task = tasks.find((item) => item.id === selectedTaskId);
    if (!task) {
      return;
    }
    setPlaygroundInput((current) => ({
      ...fillInputFromTask(task),
      message_content: current.message_content,
      requested_agent: current.requested_agent,
    }));
  }, [selectedTaskId, tasks]);

  useEffect(() => {
    void loadDataset(selectedDatasetId);
  }, [selectedDatasetId]);

  useEffect(() => {
    void loadRunHistory(selectedDatasetId, runHistoryPage, runHistoryStatus);
  }, [selectedDatasetId, runHistoryPage, runHistoryStatus]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!activeRun || !["queued", "running"].includes(activeRun.status)) {
      return;
    }
    const timer = window.setInterval(() => {
      void adminApi
        .getOrchestratorEvalRun(activeRun.id)
        .then(setActiveRun)
        .catch(() => {});
    }, 2000);
    return () => window.clearInterval(timer);
  }, [activeRun]);

  useEffect(() => {
    if (!activeRun || ["queued", "running"].includes(activeRun.status)) {
      return;
    }
    void loadRunHistory(activeRun.dataset_id, runHistoryPage, runHistoryStatus);
  }, [activeRun?.id, activeRun?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  const selectedDataset = useMemo(
    () => datasets.find((item) => item.id === selectedDatasetId) ?? null,
    [datasets, selectedDatasetId],
  );

  const caseFilterOptions = useMemo(() => {
    const agents = new Set<string>();
    const modes = new Set<string>();
    for (const item of activeRun?.case_results ?? []) {
      const agent = item.actual_route.target_agent_key;
      const mode = item.actual_route.routing_mode;
      if (agent) {
        agents.add(String(agent));
      }
      if (mode) {
        modes.add(String(mode));
      }
    }
    return {
      agents: Array.from(agents).sort(),
      modes: Array.from(modes).sort(),
    };
  }, [activeRun]);

  const visibleCaseResults = useMemo(() => {
    const query = normalizedText(caseSearch);
    return (activeRun?.case_results ?? []).filter((item) => {
      if (caseStatusFilter !== "all" && item.status !== caseStatusFilter) {
        return false;
      }
      if (
        caseAgentFilter !== "all" &&
        String(item.actual_route.target_agent_key ?? "") !== caseAgentFilter
      ) {
        return false;
      }
      if (
        caseModeFilter !== "all" &&
        String(item.actual_route.routing_mode ?? "") !== caseModeFilter
      ) {
        return false;
      }
      if (!query) {
        return true;
      }
      return [
        item.case_external_id,
        item.input.task_title,
        item.input.message_content,
        item.actual_route.routing_reason,
      ].some((value) => normalizedText(value).includes(query));
    });
  }, [
    activeRun,
    caseAgentFilter,
    caseModeFilter,
    caseSearch,
    caseStatusFilter,
  ]);

  async function handlePlaygroundRun(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      setBusy(true);
      setError(null);
      setNotice(null);
      const expectedRoute = buildExpectedRoute(
        expectedAiResponse,
        expectedTargetAgent,
        expectedMessageType,
        expectedRoutingMode,
        expectedReasonContains,
      );
      setPlaygroundResult(
        await adminApi.runOrchestratorEvalPlayground({
          input: playgroundInput,
          expected_route: expectedRoute,
          config,
        }),
      );
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось выполнить dry-run."));
    } finally {
      setBusy(false);
    }
  }

  async function handleImport(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      setBusy(true);
      setError(null);
      setNotice(null);
      const result = await adminApi.importOrchestratorEvalDataset(
        importFormat === "json"
          ? { format: "json", content: importContent }
          : {
              format: "csv",
              dataset_name: importName,
              project_id: selectedProjectId,
              content: importContent,
            },
      );
      setNotice(`Импортировано кейсов: ${result.imported_cases}.`);
      setSelectedDatasetId(result.dataset.id);
      setDatasetDetail(result.dataset);
      setDatasets(await adminApi.listOrchestratorEvalDatasets());
      setActiveTab("run");
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось импортировать набор."));
    } finally {
      setBusy(false);
    }
  }

  async function handleRun(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedDatasetId) {
      setError("Сначала выберите Orchestrator Eval набор.");
      return;
    }
    try {
      setBusy(true);
      setError(null);
      const run = await adminApi.createOrchestratorEvalRun(
        selectedDatasetId,
        config,
      );
      setActiveRun(await adminApi.getOrchestratorEvalRun(run.id));
      setActiveTab("results");
      setRunHistoryPage(1);
      setDatasets(await adminApi.listOrchestratorEvalDatasets());
      await loadRunHistory(selectedDatasetId, 1, runHistoryStatus);
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось запустить eval."));
    } finally {
      setBusy(false);
    }
  }

  async function handleOpenRun(runId: string) {
    try {
      setError(null);
      const detail = await adminApi.getOrchestratorEvalRun(runId);
      setActiveRun(detail);
      setSelectedDatasetId(detail.dataset_id);
      setActiveTab("results");
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось открыть запуск."));
    }
  }

  async function handleExport(format: "json" | "csv", runId = activeRun?.id) {
    if (!runId) {
      return;
    }
    const content = await adminApi.exportOrchestratorEvalRun(runId, format);
    downloadText(
      `orchestrator-eval-${runId}.${format}`,
      content,
      format === "json"
        ? "application/json;charset=utf-8"
        : "text/csv;charset=utf-8",
    );
  }

  async function handleDeleteRun() {
    if (!runPendingDeletion) {
      return;
    }
    try {
      setDeletingRunId(runPendingDeletion.id);
      setError(null);
      await adminApi.deleteOrchestratorEvalRun(runPendingDeletion.id);
      if (activeRun?.id === runPendingDeletion.id) {
        setActiveRun(null);
      }
      setRunPendingDeletion(null);
      setRunHistoryPage(1);
      await loadRunHistory(selectedDatasetId, 1, runHistoryStatus);
      setDatasets(await adminApi.listOrchestratorEvalDatasets());
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось удалить запуск."));
    } finally {
      setDeletingRunId(null);
    }
  }

  function renderExpectedRouteControls() {
    return (
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <label className="block">
          <span className="mb-2 block text-sm font-medium text-[#44546f]">
            AI-ответ
          </span>
          <select
            className="ui-field"
            onChange={(event) => setExpectedAiResponse(event.target.value)}
            value={expectedAiResponse}
          >
            <option value="">Не проверять</option>
            <option value="true">Нужен</option>
            <option value="false">Не нужен</option>
          </select>
        </label>
        <label className="block">
          <span className="mb-2 block text-sm font-medium text-[#44546f]">
            Expected agent
          </span>
          <input
            className="ui-field"
            onChange={(event) => setExpectedTargetAgent(event.target.value)}
            placeholder="qa"
            value={expectedTargetAgent}
          />
        </label>
        <label className="block">
          <span className="mb-2 block text-sm font-medium text-[#44546f]">
            Message type
          </span>
          <select
            className="ui-field"
            onChange={(event) => setExpectedMessageType(event.target.value)}
            value={expectedMessageType}
          >
            <option value="">Не проверять</option>
            <option value="general">general</option>
            <option value="question">question</option>
            <option value="change_proposal">change_proposal</option>
          </select>
        </label>
        <label className="block">
          <span className="mb-2 block text-sm font-medium text-[#44546f]">
            Routing mode
          </span>
          <select
            className="ui-field"
            onChange={(event) => setExpectedRoutingMode(event.target.value)}
            value={expectedRoutingMode}
          >
            <option value="">Не проверять</option>
            <option value="auto">auto</option>
            <option value="forced">forced</option>
          </select>
        </label>
        <label className="block">
          <span className="mb-2 block text-sm font-medium text-[#44546f]">
            Reason contains
          </span>
          <input
            className="ui-field"
            onChange={(event) => setExpectedReasonContains(event.target.value)}
            placeholder="forced_agent"
            value={expectedReasonContains}
          />
        </label>
      </div>
    );
  }

  function renderRouteComparison(result: OrchestratorEvalPlaygroundResultRead) {
    return (
      <section className="page-panel p-5">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="section-eyebrow">Dry-run result</p>
            <h3 className="mt-2 text-xl font-semibold text-[#172b4d]">
              {statusLabel(result.status)}
            </h3>
            <p className="mt-1 text-sm text-[#44546f]">
              latency: {formatMs(result.latency_ms)}
              {result.graph_run_id ? ` · trace: ${result.graph_run_id}` : ""}
            </p>
          </div>
          {result.graph_run_id ? (
            <Link className="ui-button-secondary" to="/admin/graph-runs">
              Открыть трассировки
            </Link>
          ) : null}
        </div>
        {result.error_message ? (
          <p className="mt-4 rounded-[10px] bg-rose-50 px-3 py-2 text-sm text-rose-700">
            {result.error_message}
          </p>
        ) : null}
        <RouteTable result={result} />
      </section>
    );
  }

  function renderPlayground() {
    return (
      <div className="space-y-5">
        <form className="page-panel space-y-5 p-5" onSubmit={handlePlaygroundRun}>
          <div className="grid gap-3 lg:grid-cols-2">
            <label className="block">
              <span className="mb-2 block text-sm font-medium text-[#44546f]">
                Проект
              </span>
              <select
                className="ui-field"
                onChange={(event) => {
                  setSelectedProjectId(event.target.value);
                  setSelectedTaskId("");
                }}
                value={selectedProjectId}
              >
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-2 block text-sm font-medium text-[#44546f]">
                Snapshot задачи
              </span>
              <select
                className="ui-field"
                onChange={(event) => setSelectedTaskId(event.target.value)}
                value={selectedTaskId}
              >
                <option value="">Ручной ввод</option>
                {tasks.map((task) => (
                  <option key={task.id} value={task.id}>
                    {task.title}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_180px]">
            <label className="block">
              <span className="mb-2 block text-sm font-medium text-[#44546f]">
                Название задачи
              </span>
              <input
                className="ui-field"
                onChange={(event) =>
                  setPlaygroundInput((current) => ({
                    ...current,
                    task_title: event.target.value,
                  }))
                }
                value={playgroundInput.task_title}
              />
            </label>
            <label className="block">
              <span className="mb-2 block text-sm font-medium text-[#44546f]">
                Статус
              </span>
              <input
                className="ui-field"
                onChange={(event) =>
                  setPlaygroundInput((current) => ({
                    ...current,
                    task_status: event.target.value,
                  }))
                }
                value={playgroundInput.task_status}
              />
            </label>
          </div>
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-[#44546f]">
              Описание задачи
            </span>
            <textarea
              className="ui-field min-h-32"
              onChange={(event) =>
                setPlaygroundInput((current) => ({
                  ...current,
                  task_content: event.target.value,
                }))
              }
              value={playgroundInput.task_content}
            />
          </label>
          <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_220px]">
            <label className="block">
              <span className="mb-2 block text-sm font-medium text-[#44546f]">
                Сообщение пользователя
              </span>
              <textarea
                className="ui-field min-h-28"
                onChange={(event) =>
                  setPlaygroundInput((current) => ({
                    ...current,
                    message_content: event.target.value,
                  }))
                }
                value={playgroundInput.message_content}
              />
            </label>
            <label className="block">
              <span className="mb-2 block text-sm font-medium text-[#44546f]">
                Forced agent
              </span>
              <input
                className="ui-field"
                onChange={(event) =>
                  setPlaygroundInput((current) => ({
                    ...current,
                    requested_agent: event.target.value || null,
                  }))
                }
                placeholder="@prefix тоже работает"
                value={playgroundInput.requested_agent ?? ""}
              />
            </label>
          </div>
          <div>
            <div className="mb-3 flex items-center justify-between gap-3">
              <h3 className="text-sm font-semibold text-[#172b4d]">
                Expected route
              </h3>
              <label className="inline-flex items-center gap-2 text-sm text-[#44546f]">
                <input
                  checked={config.compare_reason}
                  onChange={(event) =>
                    setConfig({ compare_reason: event.target.checked })
                  }
                  type="checkbox"
                />
                Проверять reason
              </label>
            </div>
            {renderExpectedRouteControls()}
          </div>
          <button className="ui-button-primary" disabled={busy} type="submit">
            {busy ? "Запуск..." : "Запустить dry-run"}
          </button>
        </form>
        {playgroundResult ? renderRouteComparison(playgroundResult) : null}
      </div>
    );
  }

  function renderImport() {
    return (
      <form className="page-panel space-y-5 p-5" onSubmit={handleImport}>
        <div className="grid gap-3 lg:grid-cols-3">
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-[#44546f]">
              Формат
            </span>
            <select
              className="ui-field"
              onChange={(event) => {
                const nextFormat = event.target.value as OrchestratorEvalImportFormat;
                setImportFormat(nextFormat);
                setImportContent(nextFormat === "json" ? JSON_TEMPLATE : CSV_TEMPLATE);
              }}
              value={importFormat}
            >
              <option value="json">JSON</option>
              <option value="csv">CSV</option>
            </select>
          </label>
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-[#44546f]">
              Название набора
            </span>
            <input
              className="ui-field"
              disabled={importFormat === "json"}
              onChange={(event) => setImportName(event.target.value)}
              value={importName}
            />
          </label>
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-[#44546f]">
              Проект для CSV
            </span>
            <select
              className="ui-field"
              disabled={importFormat === "json"}
              onChange={(event) => setSelectedProjectId(event.target.value)}
              value={selectedProjectId}
            >
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label className="block">
          <span className="mb-2 block text-sm font-medium text-[#44546f]">
            Payload
          </span>
          <textarea
            className="ui-field min-h-[420px] font-mono text-xs"
            onChange={(event) => setImportContent(event.target.value)}
            value={importContent}
          />
        </label>
        <button className="ui-button-primary" disabled={busy} type="submit">
          {busy ? "Импорт..." : "Импортировать набор"}
        </button>
      </form>
    );
  }

  function renderDatasets() {
    return (
      <section className="page-panel p-5">
        <h3 className="text-lg font-semibold text-[#172b4d]">Наборы</h3>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="text-xs uppercase tracking-[0.12em] text-[#6b778c]">
              <tr>
                <th className="py-2">Набор</th>
                <th className="py-2">Проект</th>
                <th className="py-2">Кейсы</th>
                <th className="py-2">Last run</th>
                <th className="py-2">Действия</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[rgba(9,30,66,0.08)]">
              {datasets.map((dataset) => (
                <tr key={dataset.id}>
                  <td className="py-3 font-semibold text-[#172b4d]">
                    {dataset.name}
                  </td>
                  <td className="py-3 text-[#44546f]">
                    {dataset.project_name ?? dataset.project_id}
                  </td>
                  <td className="py-3 text-[#44546f]">{dataset.cases_total}</td>
                  <td className="py-3 text-[#44546f]">
                    {statusLabel(dataset.last_run_status)}
                  </td>
                  <td className="py-3">
                    <button
                      className="ui-button-secondary"
                      onClick={() => {
                        setSelectedDatasetId(dataset.id);
                        setActiveTab("run");
                      }}
                      type="button"
                    >
                      Выбрать
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {datasets.length === 0 ? (
            <p className="rounded-[12px] border border-dashed border-[rgba(9,30,66,0.14)] p-5 text-sm text-[#44546f]">
              Наборы Orchestrator Eval пока не импортированы.
            </p>
          ) : null}
        </div>
      </section>
    );
  }

  function renderRun() {
    return (
      <div className="space-y-5">
        <form className="page-panel space-y-5 p-5" onSubmit={handleRun}>
          <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_220px]">
            <label className="block">
              <span className="mb-2 block text-sm font-medium text-[#44546f]">
                Набор
              </span>
              <select
                className="ui-field"
                onChange={(event) => {
                  setSelectedDatasetId(event.target.value);
                  setRunHistoryPage(1);
                }}
                value={selectedDatasetId}
              >
                {datasets.map((dataset) => (
                  <option key={dataset.id} value={dataset.id}>
                    {dataset.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="mt-8 inline-flex items-center gap-2 text-sm text-[#44546f]">
              <input
                checked={config.compare_reason}
                onChange={(event) =>
                  setConfig({ compare_reason: event.target.checked })
                }
                type="checkbox"
              />
              Проверять reason_contains
            </label>
          </div>
          <div className="grid gap-3 md:grid-cols-3">
            <MetricTile label="Кейсы" value={datasetDetail?.cases_total ?? 0} />
            <MetricTile label="Проект" value={selectedDataset?.project_name ?? "н/д"} />
            <MetricTile
              label="Last run"
              value={statusLabel(selectedDataset?.last_run_status)}
            />
          </div>
          <button
            className="ui-button-primary"
            disabled={busy || !selectedDatasetId}
            type="submit"
          >
            {busy ? "Запуск..." : "Запустить Orchestrator Eval"}
          </button>
        </form>
        {renderRunHistory()}
      </div>
    );
  }

  function renderRunHistory() {
    const totalPages = runHistory
      ? Math.max(1, Math.ceil(runHistory.total / runHistory.page_size))
      : 1;
    return (
      <section className="page-panel p-5">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <h3 className="text-lg font-semibold text-[#172b4d]">
            История запусков
          </h3>
          <div className="flex flex-wrap gap-2">
            <select
              className="ui-field w-auto min-w-40"
              onChange={(event) => {
                setRunHistoryPage(1);
                setRunHistoryStatus(event.target.value as RunStatusFilter);
              }}
              value={runHistoryStatus}
            >
              <option value="all">Все статусы</option>
              <option value="queued">В очереди</option>
              <option value="running">Выполняется</option>
              <option value="success">Готово</option>
              <option value="error">Ошибка</option>
            </select>
            <button
              className="ui-button-secondary"
              disabled={runHistoryLoading}
              onClick={() => void loadRunHistory(selectedDatasetId)}
              type="button"
            >
              Обновить
            </button>
          </div>
        </div>
        <div className="mt-4 space-y-3">
          {(runHistory?.items ?? []).map((run) => {
            const metrics = run.summary_metrics ?? {};
            const canDelete = !["queued", "running"].includes(run.status);
            return (
              <article
                className="rounded-[12px] border border-[rgba(9,30,66,0.1)] bg-[#fafbfc] p-4"
                key={run.id}
              >
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <p className="font-semibold text-[#172b4d]">
                      {statusLabel(run.status)} · {formatDateTimeFull(run.created_at)}
                    </p>
                    <p className="mt-1 text-sm text-[#44546f]">
                      pass: {metricValue(metrics.pass_rate)}
                      {" · "}failed: {metricValue(metrics.failed)}
                      {" · "}errors: {metricValue(metrics.errors)}
                      {" · "}latency: {formatMs(run.latency_ms)}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      className="ui-button-secondary"
                      onClick={() => void handleOpenRun(run.id)}
                      type="button"
                    >
                      Открыть
                    </button>
                    <button
                      className="ui-button-secondary"
                      onClick={() => void handleExport("json", run.id)}
                      type="button"
                    >
                      JSON
                    </button>
                    <button
                      className="ui-button-secondary"
                      onClick={() => void handleExport("csv", run.id)}
                      type="button"
                    >
                      CSV
                    </button>
                    <button
                      className="ui-button-danger"
                      disabled={!canDelete}
                      onClick={() => setRunPendingDeletion(run)}
                      type="button"
                    >
                      Удалить
                    </button>
                  </div>
                </div>
              </article>
            );
          })}
          {!runHistoryLoading && (runHistory?.items.length ?? 0) === 0 ? (
            <p className="rounded-[12px] border border-dashed border-[rgba(9,30,66,0.14)] p-5 text-sm text-[#44546f]">
              Для выбранного набора запусков нет.
            </p>
          ) : null}
        </div>
        {runHistory ? (
          <div className="mt-4 flex items-center justify-between text-sm text-[#44546f]">
            <span>
              Всего: {runHistory.total}. Страница {runHistory.page} из {totalPages}.
            </span>
            <div className="flex gap-2">
              <button
                className="ui-button-secondary"
                disabled={runHistory.page <= 1}
                onClick={() => setRunHistoryPage(runHistory.page - 1)}
                type="button"
              >
                Назад
              </button>
              <button
                className="ui-button-secondary"
                disabled={runHistory.page >= totalPages}
                onClick={() => setRunHistoryPage(runHistory.page + 1)}
                type="button"
              >
                Вперед
              </button>
            </div>
          </div>
        ) : null}
      </section>
    );
  }

  function renderCaseFilters() {
    return (
      <section className="page-panel p-5">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-[#44546f]">
              Status
            </span>
            <select
              className="ui-field"
              onChange={(event) =>
                setCaseStatusFilter(event.target.value as CaseStatusFilter)
              }
              value={caseStatusFilter}
            >
              <option value="all">Все</option>
              <option value="passed">Passed</option>
              <option value="failed">Failed</option>
              <option value="error">Error</option>
            </select>
          </label>
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-[#44546f]">
              Agent
            </span>
            <select
              className="ui-field"
              onChange={(event) => setCaseAgentFilter(event.target.value)}
              value={caseAgentFilter}
            >
              <option value="all">Все</option>
              {caseFilterOptions.agents.map((agent) => (
                <option key={agent} value={agent}>
                  {agent}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-[#44546f]">
              Mode
            </span>
            <select
              className="ui-field"
              onChange={(event) => setCaseModeFilter(event.target.value)}
              value={caseModeFilter}
            >
              <option value="all">Все</option>
              {caseFilterOptions.modes.map((mode) => (
                <option key={mode} value={mode}>
                  {mode}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-[#44546f]">
              Поиск
            </span>
            <input
              className="ui-field"
              onChange={(event) => setCaseSearch(event.target.value)}
              placeholder="case id, сообщение, reason"
              value={caseSearch}
            />
          </label>
        </div>
      </section>
    );
  }

  function renderResults() {
    if (!activeRun) {
      return (
        <div className="space-y-5">
          <p className="page-panel p-5 text-sm text-[#44546f]">
            Запустите эксперимент или откройте сохранённый запуск из истории.
          </p>
          {renderRunHistory()}
        </div>
      );
    }

    const metrics = activeRun.summary_metrics ?? {};
    return (
      <div className="space-y-5">
        <section className="page-panel p-5">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="section-eyebrow">Run status</p>
              <h3 className="mt-2 text-2xl font-semibold text-[#172b4d]">
                {statusLabel(activeRun.status)}
              </h3>
              <p className="mt-1 text-sm text-[#44546f]">
                {activeRun.started_at
                  ? `Старт: ${formatDateTimeFull(activeRun.started_at)}`
                  : "Ожидает запуска"}
                {" · "}latency: {formatMs(activeRun.latency_ms)}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                className="ui-button-secondary"
                onClick={() => void handleExport("json")}
                type="button"
              >
                Export JSON
              </button>
              <button
                className="ui-button-secondary"
                onClick={() => void handleExport("csv")}
                type="button"
              >
                Export CSV
              </button>
            </div>
          </div>
        </section>
        {renderRunHistory()}
        <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <MetricTile label="Total" value={metrics.total} />
          <MetricTile label="Pass rate" value={metrics.pass_rate} />
          <MetricTile label="Failed" value={metrics.failed} />
          <MetricTile label="Errors" value={metrics.errors} />
          <MetricTile label="p95 latency" value={formatMs(metrics.p95_latency_ms as number)} />
          <MetricTile label="Tokens" value={metrics.total_tokens} />
          <MetricTile label="Cost" value={metrics.estimated_cost_usd ?? "н/д"} />
          <MetricTile label="Avg latency" value={formatMs(metrics.avg_latency_ms as number)} />
        </section>
        {renderCaseFilters()}
        <section className="page-panel p-5">
          <h3 className="text-lg font-semibold text-[#172b4d]">Кейсы</h3>
          <div className="mt-4 space-y-4">
            {visibleCaseResults.map((item) => (
              <CaseResultCard item={item} key={item.id} />
            ))}
            {visibleCaseResults.length === 0 ? (
              <p className="rounded-[12px] border border-dashed border-[rgba(9,30,66,0.14)] p-5 text-sm text-[#44546f]">
                По текущим фильтрам кейсов нет.
              </p>
            ) : null}
          </div>
        </section>
      </div>
    );
  }

  if (loading) {
    return <LoadingSpinner label="Загрузка Orchestrator Eval" />;
  }

  return (
    <section className="space-y-6">
      <header className="page-panel p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="section-eyebrow">Orchestrator Eval</p>
            <h2 className="mt-2 text-2xl font-semibold text-[#172b4d]">
              Тест маршрутизации оркестратора
            </h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[#44546f]">
              Dry-run проверяет routing-only LangGraph без создания сообщений,
              предложений изменений и вопросов валидации.
            </p>
          </div>
          <nav className="flex flex-wrap gap-2" aria-label="Orchestrator Eval">
            {TABS.map((tab) => (
              <button
                className={
                  activeTab === tab.key
                    ? "ui-button-primary"
                    : "ui-button-secondary"
                }
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                type="button"
              >
                {tab.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      {error ? (
        <p className="rounded-[12px] bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p className="rounded-[12px] bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          {notice}
        </p>
      ) : null}

      {activeTab === "playground" ? renderPlayground() : null}
      {activeTab === "import" ? renderImport() : null}
      {activeTab === "datasets" ? renderDatasets() : null}
      {activeTab === "run" ? renderRun() : null}
      {activeTab === "results" ? renderResults() : null}

      <ConfirmDialog
        busy={deletingRunId === runPendingDeletion?.id}
        confirmLabel="Удалить запуск"
        description={
          runPendingDeletion
            ? `Удалить сохранённый Orchestrator Eval запуск от ${formatDateTimeFull(
                runPendingDeletion.created_at,
              )}? Набор данных останется доступен.`
            : ""
        }
        destructive
        onClose={() => {
          if (!deletingRunId) {
            setRunPendingDeletion(null);
          }
        }}
        onConfirm={() => void handleDeleteRun()}
        open={runPendingDeletion !== null}
        title="Удаление запуска"
      />
    </section>
  );
}

function MetricTile({ label, value }: { label: string; value: unknown }) {
  return (
    <article className="metric-tile">
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[#6b778c]">
        {label}
      </p>
      <p className="mt-2 text-xl font-semibold text-[#172b4d]">
        {metricValue(value)}
      </p>
    </article>
  );
}

function RouteTable({
  result,
}: {
  result: Pick<
    OrchestratorEvalPlaygroundResultRead,
    "actual_route" | "expected_route" | "metrics"
  >;
}) {
  const matches = asRecord(result.metrics.field_matches);
  const rows = [
    ["ai_response_required", "AI-ответ"],
    ["target_agent_key", "Agent"],
    ["message_type", "Message type"],
    ["routing_mode", "Mode"],
    ["reason_contains", "Reason contains"],
  ];
  return (
    <div className="mt-4 overflow-x-auto">
      <table className="w-full min-w-[720px] text-left text-sm">
        <thead className="text-xs uppercase tracking-[0.12em] text-[#6b778c]">
          <tr>
            <th className="py-2">Поле</th>
            <th className="py-2">Expected</th>
            <th className="py-2">Actual</th>
            <th className="py-2">Match</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[rgba(9,30,66,0.08)]">
          {rows.map(([field, label]) => (
            <tr key={field}>
              <td className="py-3 font-medium text-[#172b4d]">{label}</td>
              <td className="py-3 text-[#44546f]">
                {metricValue(result.expected_route[field])}
              </td>
              <td className="py-3 text-[#44546f]">
                {field === "reason_contains"
                  ? shortText(result.actual_route.routing_reason, 140)
                  : metricValue(result.actual_route[field])}
              </td>
              <td className="py-3 text-[#44546f]">
                {field in matches ? (matches[field] ? "yes" : "no") : "н/д"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CaseResultCard({ item }: { item: OrchestratorEvalCaseResultRead }) {
  return (
    <article className="rounded-[12px] border border-[rgba(9,30,66,0.1)] bg-[#fafbfc] p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="font-semibold text-[#172b4d]">{item.case_external_id}</p>
          <p className="mt-1 text-sm text-[#44546f]">
            {shortText(item.input.message_content, 260)}
          </p>
        </div>
        <p className="text-sm text-[#44546f]">
          {statusLabel(item.status)}
          {" · "}agent: {metricValue(item.actual_route.target_agent_key)}
          {" · "}mode: {metricValue(item.actual_route.routing_mode)}
        </p>
      </div>
      <RouteTable result={item} />
      <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-[#44546f]">
        {item.graph_run_id ? (
          <Link className="ui-button-secondary" to="/admin/graph-runs">
            Trace {item.graph_run_id.slice(0, 8)}
          </Link>
        ) : null}
        {item.error_message ? (
          <span className="rounded-[10px] bg-rose-50 px-3 py-2 text-rose-700">
            {item.error_message}
          </span>
        ) : null}
      </div>
    </article>
  );
}
