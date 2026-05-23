import { useEffect, useMemo, useState } from "react";

import {
  adminApi,
  type ProviderConfigRead,
  type RagEvalDatasetDetailRead,
  type RagEvalDatasetRead,
  type RagEvalImportFormat,
  type RagEvalIndexingMode,
  type RagEvalRunConfig,
  type RagEvalRunListItemRead,
  type RagEvalRunPageRead,
  type RagEvalRunRead,
  type RagEvalRunStatus,
} from "@/api/adminApi";
import { projectsApi, type ProjectRead } from "@/api/projectsApi";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { LoadingSpinner } from "@/shared/components/LoadingSpinner";
import { getApiErrorMessage } from "@/shared/lib/apiError";
import { formatDateTimeFull, getProviderKindLabel } from "@/shared/lib/locale";

type RagEvalTab = "import" | "datasets" | "run" | "results";
type RunStatusFilter = RagEvalRunStatus | "all";
type CaseStatusFilter = "all" | "success" | "error";
type RecallFilter = "all" | "hit" | "miss";
type NoContextFilter = "all" | "yes" | "no";
type CaseSortKey =
  | "case_external_id"
  | "status"
  | "recall_at_5"
  | "mrr"
  | "retrieval_latency_ms"
  | "created_at";
type SortDirection = "asc" | "desc";
type RagEvalCaseResult = RagEvalRunRead["case_results"][number];

const TABS: Array<{ key: RagEvalTab; label: string }> = [
  { key: "import", label: "Импорт" },
  { key: "datasets", label: "Наборы" },
  { key: "run", label: "Запуск" },
  { key: "results", label: "Результаты" },
];

const RUN_HISTORY_PAGE_SIZE = 10;

const RUN_STATUS_OPTIONS: Array<{ value: RunStatusFilter; label: string }> = [
  { value: "all", label: "Все статусы" },
  { value: "queued", label: "В очереди" },
  { value: "running", label: "Выполняется" },
  { value: "success", label: "Готово" },
  { value: "error", label: "Ошибка" },
];

const CASE_SORT_OPTIONS: Array<{ value: CaseSortKey; label: string }> = [
  { value: "case_external_id", label: "Case external id" },
  { value: "status", label: "Status" },
  { value: "recall_at_5", label: "Recall@5" },
  { value: "mrr", label: "MRR" },
  { value: "retrieval_latency_ms", label: "Retrieval latency" },
  { value: "created_at", label: "Created at" },
];

const DEFAULT_CONFIG: RagEvalRunConfig = {
  indexing_mode: "all",
  retrieval_limit: 5,
  use_query_rewriter: true,
  use_hybrid_rerank: true,
  include_cross_task: true,
  include_current_task_content: false,
  run_answer_agent: true,
  run_llm_judge: true,
  judge_provider_config_ids: [],
  run_bm25_baseline: true,
  min_score_override: null,
};

type RagEvalBooleanConfigKey =
  | "use_query_rewriter"
  | "use_hybrid_rerank"
  | "include_cross_task"
  | "include_current_task_content"
  | "run_answer_agent"
  | "run_llm_judge"
  | "run_bm25_baseline";

const BOOLEAN_CONFIG_OPTIONS: Array<{
  key: RagEvalBooleanConfigKey;
  label: string;
}> = [
  { key: "use_query_rewriter", label: "Query rewriter" },
  { key: "use_hybrid_rerank", label: "Hybrid rerank" },
  { key: "include_cross_task", label: "Cross-task context" },
  { key: "include_current_task_content", label: "Текст текущей задачи" },
  { key: "run_answer_agent", label: "QA answer agent" },
  { key: "run_llm_judge", label: "LLM judge" },
  { key: "run_bm25_baseline", label: "BM25 baseline" },
];

const JSON_TEMPLATE = `{
  "dataset_name": "RAG eval set",
  "project_id": "project-id",
  "tasks": [
    {
      "external_id": "task-auth-1",
      "title": "Авторизация",
      "content": "Описание задачи...",
      "tags": ["auth", "security"],
      "attachments": [
        {
          "filename": "requirements.txt",
          "content_type": "text/plain",
          "content": "Текстовое вложение..."
        }
      ]
    }
  ],
  "cases": [
    {
      "external_id": "case-1",
      "task_external_id": "task-auth-1",
      "question": "Какие требования к авторизации?",
      "expected_answer": "Краткий эталон или критерии ответа.",
      "expected_relevant": [
        {
          "task_external_id": "task-auth-1",
          "source_type": "task_content",
          "chunk_index": 0,
          "text_contains": "ключевой фрагмент"
        }
      ]
    }
  ]
}`;

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

function statusLabel(status: string | null) {
  switch (status) {
    case "queued":
      return "В очереди";
    case "running":
      return "Выполняется";
    case "success":
      return "Готово";
    case "error":
      return "Ошибка";
    default:
      return "н/д";
  }
}

function asRecord(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}

function asString(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return "н/д";
  }
  return String(value);
}

function asNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function asBoolean(value: unknown): boolean | null {
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "string") {
    if (value === "true") {
      return true;
    }
    if (value === "false") {
      return false;
    }
  }
  return null;
}

function normalizedText(value: unknown) {
  return String(value ?? "").toLocaleLowerCase("ru-RU");
}

function shortText(value: unknown, maxLength = 280) {
  const normalized = String(value ?? "")
    .replace(/\s+/g, " ")
    .trim();
  if (normalized.length <= maxLength) {
    return normalized || "Контент не сохранён.";
  }
  return `${normalized.slice(0, maxLength).trim()}...`;
}

function formatMs(value: number | null | undefined) {
  return value === null || value === undefined
    ? "н/д"
    : `${value.toLocaleString("ru-RU")} мс`;
}

function formatConfigSnapshot(config: RagEvalRunConfig) {
  return [
    `index: ${config.indexing_mode}`,
    `limit: ${config.retrieval_limit}`,
    config.use_query_rewriter ? "rewriter on" : "rewriter off",
    config.use_hybrid_rerank ? "rerank on" : "rerank off",
    config.run_bm25_baseline ? "BM25 on" : "BM25 off",
    config.run_answer_agent ? "QA on" : "QA off",
    config.run_llm_judge ? "judge on" : "judge off",
    config.judge_provider_config_ids.length
      ? `judges: ${config.judge_provider_config_ids.length}`
      : "judge default",
  ].join(" · ");
}

function judgeRunsFromPayload(value: unknown): Array<Record<string, unknown>> {
  const payload = asRecord(value);
  return Array.isArray(payload.judge_runs)
    ? payload.judge_runs.map(asRecord)
    : [];
}

function correctnessSummary(metrics: Record<string, unknown> | null) {
  const correctness = asRecord(metrics?.correctness);
  const entries = Object.entries(correctness);
  if (entries.length === 0) {
    return "judge: н/д";
  }
  return entries
    .map(
      ([key, value]) => `${key}: ${Number(value || 0).toLocaleString("ru-RU")}`,
    )
    .join(" · ");
}

function compareNullable(
  left: string | number | null,
  right: string | number | null,
) {
  if (left === null && right === null) {
    return 0;
  }
  if (left === null) {
    return 1;
  }
  if (right === null) {
    return -1;
  }
  if (typeof left === "number" && typeof right === "number") {
    return left - right;
  }
  return String(left).localeCompare(String(right), "ru-RU", {
    numeric: true,
    sensitivity: "base",
  });
}

function getCaseSortValue(item: RagEvalCaseResult, sortKey: CaseSortKey) {
  switch (sortKey) {
    case "case_external_id":
      return item.case_external_id;
    case "status":
      return item.status;
    case "recall_at_5":
      return asBoolean(item.metrics.recall_at_5) ? 1 : 0;
    case "mrr":
      return asNumber(item.metrics.mrr);
    case "retrieval_latency_ms":
      return item.retrieval_latency_ms;
    case "created_at": {
      const timestamp = Date.parse(item.created_at);
      return Number.isFinite(timestamp) ? timestamp : null;
    }
    default:
      return item.case_external_id;
  }
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

export default function RagEvalPage() {
  const [activeTab, setActiveTab] = useState<RagEvalTab>("import");
  const [projects, setProjects] = useState<ProjectRead[]>([]);
  const [datasets, setDatasets] = useState<RagEvalDatasetRead[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [selectedDatasetId, setSelectedDatasetId] = useState("");
  const [datasetDetail, setDatasetDetail] =
    useState<RagEvalDatasetDetailRead | null>(null);
  const [activeRun, setActiveRun] = useState<RagEvalRunRead | null>(null);
  const [runHistory, setRunHistory] = useState<RagEvalRunPageRead | null>(null);
  const [runHistoryPage, setRunHistoryPage] = useState(1);
  const [runHistoryStatus, setRunHistoryStatus] =
    useState<RunStatusFilter>("all");
  const [runHistoryLoading, setRunHistoryLoading] = useState(false);
  const [runPendingDeletion, setRunPendingDeletion] =
    useState<RagEvalRunListItemRead | null>(null);
  const [deletingRunId, setDeletingRunId] = useState<string | null>(null);
  const [caseStatusFilter, setCaseStatusFilter] =
    useState<CaseStatusFilter>("all");
  const [recallFilter, setRecallFilter] = useState<RecallFilter>("all");
  const [correctnessFilter, setCorrectnessFilter] = useState("all");
  const [groundednessFilter, setGroundednessFilter] = useState("all");
  const [noContextFilter, setNoContextFilter] =
    useState<NoContextFilter>("all");
  const [caseSearch, setCaseSearch] = useState("");
  const [caseSortKey, setCaseSortKey] =
    useState<CaseSortKey>("case_external_id");
  const [caseSortDirection, setCaseSortDirection] =
    useState<SortDirection>("asc");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [importFormat, setImportFormat] = useState<RagEvalImportFormat>("json");
  const [importName, setImportName] = useState("RAG eval set");
  const [importContent, setImportContent] = useState(JSON_TEMPLATE);
  const [config, setConfig] = useState<RagEvalRunConfig>(DEFAULT_CONFIG);
  const [providers, setProviders] = useState<ProviderConfigRead[]>([]);

  async function loadBootstrap() {
    try {
      setLoading(true);
      setError(null);
      const [projectList, datasetList, providerList] = await Promise.all([
        projectsApi.list(),
        adminApi.listRagEvalDatasets(),
        adminApi.listProviders(),
      ]);
      setProjects(projectList);
      setDatasets(datasetList);
      setProviders(providerList.filter((provider) => provider.enabled));
      setSelectedProjectId((current) => current || projectList[0]?.id || "");
      setSelectedDatasetId((current) => current || datasetList[0]?.id || "");
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось загрузить RAG Eval."));
    } finally {
      setLoading(false);
    }
  }

  async function loadDataset(datasetId: string) {
    if (!datasetId) {
      setDatasetDetail(null);
      return;
    }
    try {
      setError(null);
      const detail = await adminApi.getRagEvalDataset(datasetId);
      setDatasetDetail(detail);
    } catch (caught) {
      setError(
        getApiErrorMessage(caught, "Не удалось загрузить набор RAG Eval."),
      );
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
      const history = await adminApi.listRagEvalRuns(datasetId, {
        page,
        size: RUN_HISTORY_PAGE_SIZE,
        ...(status !== "all" ? { status } : {}),
      });
      setRunHistory(history);
    } catch (caught) {
      setError(
        getApiErrorMessage(caught, "Не удалось загрузить историю RAG Eval."),
      );
    } finally {
      setRunHistoryLoading(false);
    }
  }

  useEffect(() => {
    void loadBootstrap();
  }, []);

  useEffect(() => {
    void loadDataset(selectedDatasetId);
  }, [selectedDatasetId]);

  useEffect(() => {
    void loadRunHistory(selectedDatasetId, runHistoryPage, runHistoryStatus);
  }, [selectedDatasetId, runHistoryPage, runHistoryStatus]);

  useEffect(() => {
    if (!activeRun || !["queued", "running"].includes(activeRun.status)) {
      return;
    }
    const timer = window.setInterval(() => {
      void adminApi
        .getRagEvalRun(activeRun.id)
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
  }, [activeRun?.id, activeRun?.status]);

  const selectedDataset = useMemo(
    () => datasets.find((item) => item.id === selectedDatasetId) ?? null,
    [datasets, selectedDatasetId],
  );

  const caseFilterOptions = useMemo(() => {
    const correctness = new Set<string>();
    const groundedness = new Set<string>();
    for (const item of activeRun?.case_results ?? []) {
      const itemCorrectness =
        item.metrics.correctness ?? item.judge_payload?.correctness;
      const itemGroundedness =
        item.metrics.groundedness ?? item.judge_payload?.groundedness;
      if (itemCorrectness) {
        correctness.add(String(itemCorrectness));
      }
      if (itemGroundedness) {
        groundedness.add(String(itemGroundedness));
      }
    }
    return {
      correctness: Array.from(correctness).sort(),
      groundedness: Array.from(groundedness).sort(),
    };
  }, [activeRun]);

  const visibleCaseResults = useMemo(() => {
    const query = normalizedText(caseSearch.trim());
    return [...(activeRun?.case_results ?? [])]
      .filter((item) => {
        if (caseStatusFilter !== "all" && item.status !== caseStatusFilter) {
          return false;
        }
        const recallAt5 = asBoolean(item.metrics.recall_at_5);
        if (recallFilter === "hit" && recallAt5 !== true) {
          return false;
        }
        if (recallFilter === "miss" && recallAt5 === true) {
          return false;
        }
        const correctness = String(
          item.metrics.correctness ?? item.judge_payload?.correctness ?? "",
        );
        if (correctnessFilter !== "all" && correctness !== correctnessFilter) {
          return false;
        }
        const groundedness = String(
          item.metrics.groundedness ?? item.judge_payload?.groundedness ?? "",
        );
        if (
          groundednessFilter !== "all" &&
          groundedness !== groundednessFilter
        ) {
          return false;
        }
        const noContext = asBoolean(item.metrics.no_context);
        if (noContextFilter === "yes" && noContext !== true) {
          return false;
        }
        if (noContextFilter === "no" && noContext === true) {
          return false;
        }
        if (!query) {
          return true;
        }
        return [
          item.case_external_id,
          item.task_external_id,
          item.question,
          item.answer_text,
        ].some((value) => normalizedText(value).includes(query));
      })
      .sort((left, right) => {
        const compared = compareNullable(
          getCaseSortValue(left, caseSortKey),
          getCaseSortValue(right, caseSortKey),
        );
        return caseSortDirection === "asc" ? compared : -compared;
      });
  }, [
    activeRun,
    caseSearch,
    caseSortDirection,
    caseSortKey,
    caseStatusFilter,
    correctnessFilter,
    groundednessFilter,
    noContextFilter,
    recallFilter,
  ]);

  const judgeProviderSelectionError =
    config.run_llm_judge &&
    config.judge_provider_config_ids.length > 3
      ? "Выберите не больше 3 LLM-профилей или снимите все для runtime default."
      : null;

  async function handleImport(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      setBusy(true);
      setError(null);
      setNotice(null);
      const result = await adminApi.importRagEvalDataset(
        importFormat === "json"
          ? { format: "json", content: importContent }
          : {
              format: "csv",
              dataset_name: importName,
              project_id: selectedProjectId,
              content: importContent,
            },
      );
      setNotice(
        `Импортировано: задач создано ${result.created_tasks}, обновлено ${result.updated_tasks}, кейсов ${result.imported_cases}.`,
      );
      setSelectedDatasetId(result.dataset.id);
      setDatasetDetail(result.dataset);
      setActiveTab("run");
      setDatasets(await adminApi.listRagEvalDatasets());
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось импортировать набор."));
    } finally {
      setBusy(false);
    }
  }

  async function handleRun(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedDatasetId) {
      setError("Сначала выберите RAG Eval набор.");
      return;
    }
    if (judgeProviderSelectionError) {
      setError(judgeProviderSelectionError);
      return;
    }
    try {
      setBusy(true);
      setError(null);
      const run = await adminApi.createRagEvalRun(selectedDatasetId, config);
      const runDetail = await adminApi.getRagEvalRun(run.id);
      setActiveRun(runDetail);
      setActiveTab("results");
      setDatasets(await adminApi.listRagEvalDatasets());
      setRunHistoryPage(1);
      await loadRunHistory(selectedDatasetId, 1, runHistoryStatus);
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось запустить RAG Eval."));
    } finally {
      setBusy(false);
    }
  }

  async function handleExport(format: "json" | "csv", runId = activeRun?.id) {
    if (!runId) {
      return;
    }
    const content = await adminApi.exportRagEvalRun(runId, format);
    downloadText(
      `rag-eval-${runId}.${format}`,
      content,
      format === "json"
        ? "application/json;charset=utf-8"
        : "text/csv;charset=utf-8",
    );
  }

  async function handleOpenRun(runId: string) {
    try {
      setError(null);
      const detail = await adminApi.getRagEvalRun(runId);
      setActiveRun(detail);
      setSelectedDatasetId(detail.dataset_id);
      setActiveTab("results");
    } catch (caught) {
      setError(
        getApiErrorMessage(caught, "Не удалось открыть RAG Eval запуск."),
      );
    }
  }

  async function handleDeleteRun() {
    if (!runPendingDeletion) {
      return;
    }
    try {
      setDeletingRunId(runPendingDeletion.id);
      setError(null);
      await adminApi.deleteRagEvalRun(runPendingDeletion.id);
      if (activeRun?.id === runPendingDeletion.id) {
        setActiveRun(null);
      }
      setRunPendingDeletion(null);
      setRunHistoryPage(1);
      await loadRunHistory(selectedDatasetId, 1, runHistoryStatus);
      setDatasets(await adminApi.listRagEvalDatasets());
    } catch (caught) {
      setError(
        getApiErrorMessage(caught, "Не удалось удалить RAG Eval запуск."),
      );
    } finally {
      setDeletingRunId(null);
    }
  }

  function renderImport() {
    return (
      <form
        className="rounded-[20px] border border-[rgba(9,30,66,0.12)] bg-white p-6"
        onSubmit={handleImport}
      >
        <div className="grid gap-4 lg:grid-cols-3">
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-[#44546f]">
              Формат
            </span>
            <select
              className="ui-field"
              onChange={(event) =>
                setImportFormat(event.target.value as RagEvalImportFormat)
              }
              value={importFormat}
            >
              <option value="json">JSON</option>
              <option value="csv">CSV</option>
            </select>
          </label>
          {importFormat === "csv" ? (
            <>
              <label className="block">
                <span className="mb-2 block text-sm font-medium text-[#44546f]">
                  Название набора
                </span>
                <input
                  className="ui-field"
                  onChange={(event) => setImportName(event.target.value)}
                  value={importName}
                />
              </label>
              <label className="block">
                <span className="mb-2 block text-sm font-medium text-[#44546f]">
                  Eval-проект
                </span>
                <select
                  className="ui-field"
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
            </>
          ) : null}
        </div>

        <label className="mt-5 block">
          <span className="mb-2 block text-sm font-medium text-[#44546f]">
            Содержимое импорта
          </span>
          <textarea
            className="ui-field min-h-[360px] font-mono text-sm"
            onChange={(event) => setImportContent(event.target.value)}
            spellCheck={false}
            value={importContent}
          />
        </label>

        <div className="mt-5 flex flex-wrap gap-3">
          <button className="ui-button-primary" disabled={busy} type="submit">
            {busy ? "Импорт..." : "Импортировать набор"}
          </button>
          <button
            className="ui-button-secondary"
            onClick={() => setImportContent(JSON_TEMPLATE)}
            type="button"
          >
            Вставить JSON-шаблон
          </button>
        </div>
      </form>
    );
  }

  function renderDatasets() {
    return (
      <div className="space-y-4">
        {datasets.length === 0 ? (
          <p className="rounded-[16px] border border-dashed border-[rgba(9,30,66,0.16)] bg-white p-6 text-sm text-[#44546f]">
            Наборы RAG Eval пока не импортированы.
          </p>
        ) : null}
        {datasets.map((dataset) => (
          <article
            key={dataset.id}
            className="rounded-[18px] border border-[rgba(9,30,66,0.12)] bg-white p-5"
          >
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <h3 className="text-lg font-semibold text-[#172b4d]">
                  {dataset.name}
                </h3>
                <p className="mt-1 text-sm text-[#44546f]">
                  Проект: {dataset.project_name ?? dataset.project_id}
                  {" · "}задач: {dataset.tasks_total}
                  {" · "}кейсов: {dataset.cases_total}
                  {" · "}последний запуск:{" "}
                  {statusLabel(dataset.last_run_status)}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                {dataset.last_run_id ? (
                  <button
                    className="ui-button-secondary"
                    onClick={() =>
                      void handleOpenRun(dataset.last_run_id as string)
                    }
                    type="button"
                  >
                    Открыть последний
                  </button>
                ) : null}
                <button
                  className={
                    selectedDatasetId === dataset.id
                      ? "ui-button-primary"
                      : "ui-button-secondary"
                  }
                  onClick={() => {
                    setSelectedDatasetId(dataset.id);
                    setRunHistoryPage(1);
                    setActiveRun(null);
                    setActiveTab("run");
                  }}
                  type="button"
                >
                  Выбрать
                </button>
              </div>
            </div>
          </article>
        ))}
      </div>
    );
  }

  function renderRun() {
    return (
      <div className="space-y-5">
        <form
          className="rounded-[20px] border border-[rgba(9,30,66,0.12)] bg-white p-6"
          onSubmit={handleRun}
        >
          <div className="grid gap-4 lg:grid-cols-3">
            <label className="block lg:col-span-2">
              <span className="mb-2 block text-sm font-medium text-[#44546f]">
                Набор
              </span>
              <select
                className="ui-field"
                onChange={(event) => setSelectedDatasetId(event.target.value)}
                value={selectedDatasetId}
              >
                <option value="">Выберите набор</option>
                {datasets.map((dataset) => (
                  <option key={dataset.id} value={dataset.id}>
                    {dataset.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-2 block text-sm font-medium text-[#44546f]">
                Индексация
              </span>
              <select
                className="ui-field"
                onChange={(event) =>
                  setConfig((current) => ({
                    ...current,
                    indexing_mode: event.target.value as RagEvalIndexingMode,
                  }))
                }
                value={config.indexing_mode}
              >
                <option value="all">Все задачи</option>
                <option value="stale_only">Только stale</option>
                <option value="none">Не индексировать</option>
              </select>
            </label>
          </div>

          <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <label className="block">
              <span className="mb-2 block text-sm font-medium text-[#44546f]">
                Retrieval limit
              </span>
              <input
                className="ui-field"
                max={10}
                min={1}
                onChange={(event) =>
                  setConfig((current) => ({
                    ...current,
                    retrieval_limit: Number(event.target.value),
                  }))
                }
                type="number"
                value={config.retrieval_limit}
              />
            </label>
            <label className="block">
              <span className="mb-2 block text-sm font-medium text-[#44546f]">
                Min score override
              </span>
              <input
                className="ui-field"
                max={1}
                min={0}
                onChange={(event) =>
                  setConfig((current) => ({
                    ...current,
                    min_score_override: event.target.value
                      ? Number(event.target.value)
                      : null,
                  }))
                }
                step="0.05"
                type="number"
                value={config.min_score_override ?? ""}
              />
            </label>
          </div>

          <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {BOOLEAN_CONFIG_OPTIONS.map(({ key, label }) => (
              <label
                key={key}
                className="flex items-center justify-between gap-3 rounded-[14px] border border-[rgba(9,30,66,0.12)] bg-[#fafbfc] px-4 py-3 text-sm font-medium text-[#172b4d]"
              >
                <span>{label}</span>
                <input
                  checked={config[key]}
                  onChange={(event) =>
                    setConfig((current) => ({
                      ...current,
                      [key]: event.target.checked,
                      ...(key === "run_llm_judge" && !event.target.checked
                        ? { judge_provider_config_ids: [] }
                        : {}),
                    }))
                  }
                  type="checkbox"
                />
              </label>
            ))}
          </div>

          {config.run_llm_judge ? (
            <div className="mt-5 rounded-[14px] border border-[rgba(9,30,66,0.12)] bg-[#fafbfc] p-4">
              <div className="flex flex-col gap-1">
                <p className="text-sm font-semibold text-[#172b4d]">
                  Judge providers
                </p>
                <p className="text-sm text-[#626f86]">
                  0 профилей — runtime default. Для явного сравнения выберите от 1 до 3.
                </p>
              </div>
              <div className="mt-3 grid gap-2 md:grid-cols-3">
                {providers.map((provider) => {
                  const checked = config.judge_provider_config_ids.includes(
                    provider.id,
                  );
                  const disabled =
                    !checked && config.judge_provider_config_ids.length >= 3;
                  return (
                    <label
                      className="flex items-center gap-3 rounded-[10px] border border-[rgba(9,30,66,0.1)] bg-white px-3 py-2 text-sm text-[#172b4d]"
                      key={provider.id}
                    >
                      <input
                        checked={checked}
                        disabled={disabled}
                        onChange={(event) =>
                          setConfig((current) => ({
                            ...current,
                            judge_provider_config_ids: event.target.checked
                              ? [...current.judge_provider_config_ids, provider.id]
                              : current.judge_provider_config_ids.filter(
                                  (id) => id !== provider.id,
                                ),
                          }))
                        }
                        type="checkbox"
                      />
                      <span>
                        {provider.name} /{" "}
                        {getProviderKindLabel(provider.provider_kind)} /{" "}
                        {provider.model}
                      </span>
                    </label>
                  );
                })}
              </div>
              {judgeProviderSelectionError ? (
                <p className="mt-3 text-sm font-semibold text-[#ae2e24]">
                  {judgeProviderSelectionError}
                </p>
              ) : null}
            </div>
          ) : null}

          {datasetDetail ? (
            <p className="mt-5 text-sm text-[#44546f]">
              Выбран набор: {datasetDetail.name}. Задач:{" "}
              {datasetDetail.tasks_total}, кейсов: {datasetDetail.cases_total}.
            </p>
          ) : selectedDataset ? (
            <p className="mt-5 text-sm text-[#44546f]">
              Выбран набор: {selectedDataset.name}.
            </p>
          ) : null}

          <button
            className="mt-5 ui-button-primary"
            disabled={busy || !selectedDatasetId || Boolean(judgeProviderSelectionError)}
            type="submit"
          >
            {busy ? "Запуск..." : "Запустить RAG Eval"}
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
      <section className="rounded-[20px] border border-[rgba(9,30,66,0.12)] bg-white p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h3 className="text-lg font-semibold text-[#172b4d]">
              История запусков
            </h3>
            <p className="mt-1 text-sm text-[#44546f]">
              Сохранённые результаты выбранного RAG Eval набора.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {selectedDataset?.last_run_id ? (
              <button
                className="ui-button-secondary"
                onClick={() =>
                  void handleOpenRun(selectedDataset.last_run_id as string)
                }
                type="button"
              >
                Открыть последний
              </button>
            ) : null}
            <button
              className="ui-button-secondary"
              disabled={!selectedDatasetId || runHistoryLoading}
              onClick={() => void loadRunHistory(selectedDatasetId)}
              type="button"
            >
              Обновить
            </button>
          </div>
        </div>

        <div className="mt-5 grid gap-4 md:grid-cols-3">
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-[#44546f]">
              Статус
            </span>
            <select
              className="ui-field"
              onChange={(event) => {
                setRunHistoryStatus(event.target.value as RunStatusFilter);
                setRunHistoryPage(1);
              }}
              value={runHistoryStatus}
            >
              {RUN_STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        {!selectedDatasetId ? (
          <p className="mt-5 rounded-[14px] border border-dashed border-[rgba(9,30,66,0.16)] bg-[#fafbfc] p-4 text-sm text-[#44546f]">
            Выберите RAG Eval набор, чтобы увидеть историю запусков.
          </p>
        ) : null}

        {runHistoryLoading ? (
          <p className="mt-5 text-sm text-[#44546f]">Загрузка истории...</p>
        ) : null}

        {!runHistoryLoading &&
        selectedDatasetId &&
        (runHistory?.items.length ?? 0) === 0 ? (
          <p className="mt-5 rounded-[14px] border border-dashed border-[rgba(9,30,66,0.16)] bg-[#fafbfc] p-4 text-sm text-[#44546f]">
            Для выбранного фильтра сохранённых запусков нет.
          </p>
        ) : null}

        <div className="mt-5 space-y-3">
          {(runHistory?.items ?? []).map((run) => {
            const metrics = run.summary_metrics ?? {};
            const isActive = activeRun?.id === run.id;
            const canDelete = !["queued", "running"].includes(run.status);
            return (
              <article
                key={run.id}
                className="rounded-[16px] border border-[rgba(9,30,66,0.12)] bg-[#fafbfc] p-4"
              >
                <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={
                          isActive
                            ? "status-pill border-[#0c66e4] bg-[#e9f2ff] text-[#0055cc]"
                            : "status-pill border-[rgba(9,30,66,0.12)] bg-white text-[#44546f]"
                        }
                      >
                        {statusLabel(run.status)}
                      </span>
                      <span className="text-sm font-medium text-[#172b4d]">
                        {formatDateTimeFull(run.created_at)}
                      </span>
                    </div>
                    <p className="mt-2 text-sm text-[#44546f]">
                      latency: {formatMs(run.latency_ms)}
                      {" · "}R@5: {metricValue(metrics.recall_at_5)}
                      {" · "}MRR: {metricValue(metrics.mrr)}
                      {metrics.bm25_mrr !== undefined ? (
                        <>
                          {" · "}BM25 R@5:{" "}
                          {metricValue(metrics.bm25_recall_at_5)}
                          {" · "}BM25 MRR: {metricValue(metrics.bm25_mrr)}
                        </>
                      ) : null}
                    </p>
                    <p className="mt-1 text-sm text-[#44546f]">
                      {correctnessSummary(metrics)}
                    </p>
                    <p className="mt-2 text-xs leading-5 text-[#626f86]">
                      {formatConfigSnapshot(run.config)}
                    </p>
                    {run.error_message ? (
                      <p className="mt-3 rounded-[12px] bg-rose-50 px-3 py-2 text-sm text-rose-700">
                        {run.error_message}
                      </p>
                    ) : null}
                  </div>
                  <div className="flex shrink-0 flex-wrap gap-2">
                    <button
                      className={
                        isActive ? "ui-button-primary" : "ui-button-secondary"
                      }
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
        </div>

        {runHistory ? (
          <div className="mt-5 flex flex-col gap-3 border-t border-[rgba(9,30,66,0.08)] pt-4 text-sm text-[#44546f] sm:flex-row sm:items-center sm:justify-between">
            <span>
              Всего: {runHistory.total}. Страница {runHistory.page} из{" "}
              {totalPages}.
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
      <section className="rounded-[20px] border border-[rgba(9,30,66,0.12)] bg-white p-6">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h3 className="text-lg font-semibold text-[#172b4d]">
              Фильтры и сортировка кейсов
            </h3>
            <p className="mt-1 text-sm text-[#44546f]">
              Показано {visibleCaseResults.length} из{" "}
              {activeRun?.case_results.length ?? 0}.
            </p>
          </div>
          <button
            className="ui-button-secondary"
            onClick={() => {
              setCaseStatusFilter("all");
              setRecallFilter("all");
              setCorrectnessFilter("all");
              setGroundednessFilter("all");
              setNoContextFilter("all");
              setCaseSearch("");
              setCaseSortKey("case_external_id");
              setCaseSortDirection("asc");
            }}
            type="button"
          >
            Сбросить
          </button>
        </div>

        <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
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
              <option value="success">Success</option>
              <option value="error">Error</option>
            </select>
          </label>
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-[#44546f]">
              Recall@5
            </span>
            <select
              className="ui-field"
              onChange={(event) =>
                setRecallFilter(event.target.value as RecallFilter)
              }
              value={recallFilter}
            >
              <option value="all">Все</option>
              <option value="hit">Hit</option>
              <option value="miss">Miss</option>
            </select>
          </label>
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-[#44546f]">
              Correctness
            </span>
            <select
              className="ui-field"
              onChange={(event) => setCorrectnessFilter(event.target.value)}
              value={correctnessFilter}
            >
              <option value="all">Все</option>
              {caseFilterOptions.correctness.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-[#44546f]">
              Groundedness
            </span>
            <select
              className="ui-field"
              onChange={(event) => setGroundednessFilter(event.target.value)}
              value={groundednessFilter}
            >
              <option value="all">Все</option>
              {caseFilterOptions.groundedness.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-[#44546f]">
              No-context
            </span>
            <select
              className="ui-field"
              onChange={(event) =>
                setNoContextFilter(event.target.value as NoContextFilter)
              }
              value={noContextFilter}
            >
              <option value="all">Все</option>
              <option value="yes">Да</option>
              <option value="no">Нет</option>
            </select>
          </label>
          <label className="block xl:col-span-2">
            <span className="mb-2 block text-sm font-medium text-[#44546f]">
              Поиск
            </span>
            <input
              className="ui-field"
              onChange={(event) => setCaseSearch(event.target.value)}
              placeholder="case id, вопрос или ответ"
              value={caseSearch}
            />
          </label>
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-[#44546f]">
              Сортировка
            </span>
            <select
              className="ui-field"
              onChange={(event) =>
                setCaseSortKey(event.target.value as CaseSortKey)
              }
              value={caseSortKey}
            >
              {CASE_SORT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-[#44546f]">
              Направление
            </span>
            <select
              className="ui-field"
              onChange={(event) =>
                setCaseSortDirection(event.target.value as SortDirection)
              }
              value={caseSortDirection}
            >
              <option value="asc">По возрастанию</option>
              <option value="desc">По убыванию</option>
            </select>
          </label>
        </div>
      </section>
    );
  }

  function renderRetrievalDetails(item: RagEvalCaseResult) {
    const matchedChunkIds = new Set(
      item.matched_expected
        .map((match) => String(match.chunk_id ?? ""))
        .filter(Boolean),
    );
    const judgePayload = asRecord(item.judge_payload);
    const judgeRuns = judgeRunsFromPayload(judgePayload);
    const unsupportedClaims = Array.isArray(judgePayload.unsupported_claims)
      ? judgePayload.unsupported_claims
      : [];
    const bm25RetrievedChunks = Array.isArray(
      item.metrics.bm25_retrieved_chunks,
    )
      ? (item.metrics.bm25_retrieved_chunks as Array<Record<string, unknown>>)
      : [];
    const bm25MatchedExpected = Array.isArray(
      item.metrics.bm25_matched_expected,
    )
      ? (item.metrics.bm25_matched_expected as Array<Record<string, unknown>>)
      : [];

    return (
      <details className="mt-3">
        <summary className="cursor-pointer text-sm font-medium text-[#0c66e4]">
          Retrieval details
        </summary>
        <div className="mt-3 space-y-4 rounded-[14px] border border-[rgba(9,30,66,0.1)] bg-white p-4">
          <div className="grid gap-3 md:grid-cols-4">
            {[
              ["Retrieved", item.retrieved_chunks.length],
              ["Matched", item.matched_expected.length],
              ["First rank", metricValue(item.metrics.first_relevant_rank)],
              ["Retrieval", formatMs(item.retrieval_latency_ms)],
            ].map(([label, value]) => (
              <div
                className="rounded-[12px] border border-[rgba(9,30,66,0.08)] bg-[#fafbfc] px-3 py-2"
                key={label}
              >
                <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[#6b778c]">
                  {label}
                </p>
                <p className="mt-1 text-sm font-semibold text-[#172b4d]">
                  {value}
                </p>
              </div>
            ))}
          </div>

          <div>
            <h4 className="text-sm font-semibold text-[#172b4d]">
              Retrieved chunks
            </h4>
            {item.retrieved_chunks.length === 0 ? (
              <p className="mt-2 rounded-[12px] border border-dashed border-[rgba(9,30,66,0.16)] bg-[#fafbfc] p-3 text-sm text-[#44546f]">
                Retrieval не вернул контекст.
              </p>
            ) : (
              <div className="mt-2 overflow-x-auto">
                <table className="w-full min-w-[860px] text-left text-sm">
                  <thead className="text-xs uppercase tracking-[0.12em] text-[#6b778c]">
                    <tr>
                      <th className="py-2">Rank</th>
                      <th className="py-2">Score</th>
                      <th className="py-2">Threshold</th>
                      <th className="py-2">Source</th>
                      <th className="py-2">Task</th>
                      <th className="py-2">Chunk</th>
                      <th className="py-2">Preview</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[rgba(9,30,66,0.08)]">
                    {item.retrieved_chunks.map((chunk, index) => {
                      const chunkId = String(chunk.chunk_id ?? "");
                      const rank = index + 1;
                      const matched =
                        matchedChunkIds.has(chunkId) ||
                        item.matched_expected.some(
                          (match) => asNumber(match.rank) === rank,
                        );
                      return (
                        <tr key={`${chunkId || "chunk"}-${rank}`}>
                          <td className="py-3 font-semibold text-[#172b4d]">
                            #{rank}
                          </td>
                          <td className="py-3 text-[#44546f]">
                            {metricValue(chunk.score)}
                          </td>
                          <td className="py-3 text-[#44546f]">
                            {metricValue(chunk.threshold)}
                          </td>
                          <td className="py-3 text-[#44546f]">
                            {asString(chunk.source_type)}
                          </td>
                          <td className="py-3 text-[#44546f]">
                            {asString(chunk.task_external_id ?? chunk.task_id)}
                          </td>
                          <td className="py-3 text-[#44546f]">
                            {asString(chunk.chunk_index)}
                            {matched ? (
                              <span className="ml-2 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-700">
                                matched
                              </span>
                            ) : null}
                          </td>
                          <td className="max-w-[360px] py-3 text-[#44546f]">
                            {shortText(chunk.content)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {bm25RetrievedChunks.length || item.metrics.bm25_mrr !== undefined ? (
            <div>
              <h4 className="text-sm font-semibold text-[#172b4d]">
                BM25 retrieved chunks
              </h4>
              <div className="mt-2 grid gap-3 md:grid-cols-4">
                {[
                  ["BM25 R@5", metricValue(item.metrics.bm25_recall_at_5)],
                  [
                    "BM25 Precision@k",
                    metricValue(item.metrics.bm25_precision_at_k),
                  ],
                  ["BM25 MRR", metricValue(item.metrics.bm25_mrr)],
                  [
                    "BM25 first rank",
                    metricValue(item.metrics.bm25_first_relevant_rank),
                  ],
                ].map(([label, value]) => (
                  <div
                    className="rounded-[12px] border border-[rgba(9,30,66,0.08)] bg-[#fafbfc] px-3 py-2"
                    key={label}
                  >
                    <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[#6b778c]">
                      {label}
                    </p>
                    <p className="mt-1 text-sm font-semibold text-[#172b4d]">
                      {value}
                    </p>
                  </div>
                ))}
              </div>
              {bm25RetrievedChunks.length === 0 ? (
                <p className="mt-2 rounded-[12px] border border-dashed border-[rgba(9,30,66,0.16)] bg-[#fafbfc] p-3 text-sm text-[#44546f]">
                  BM25 baseline не вернул контекст.
                </p>
              ) : (
                <div className="mt-2 overflow-x-auto">
                  <table className="w-full min-w-[760px] text-left text-sm">
                    <thead className="text-xs uppercase tracking-[0.12em] text-[#6b778c]">
                      <tr>
                        <th className="py-2">Rank</th>
                        <th className="py-2">Score</th>
                        <th className="py-2">Source</th>
                        <th className="py-2">Task</th>
                        <th className="py-2">Chunk</th>
                        <th className="py-2">Preview</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[rgba(9,30,66,0.08)]">
                      {bm25RetrievedChunks.map((chunk, index) => {
                        const chunkId = String(chunk.chunk_id ?? "");
                        const rank = index + 1;
                        const matched = bm25MatchedExpected.some(
                          (match) =>
                            String(match.chunk_id ?? "") === chunkId ||
                            asNumber(match.rank) === rank,
                        );
                        return (
                          <tr key={`${chunkId || "bm25-chunk"}-${rank}`}>
                            <td className="py-3 font-semibold text-[#172b4d]">
                              #{rank}
                            </td>
                            <td className="py-3 text-[#44546f]">
                              {metricValue(chunk.score)}
                            </td>
                            <td className="py-3 text-[#44546f]">
                              {asString(chunk.source_type)}
                            </td>
                            <td className="py-3 text-[#44546f]">
                              {asString(
                                chunk.task_external_id ?? chunk.task_id,
                              )}
                            </td>
                            <td className="py-3 text-[#44546f]">
                              {asString(chunk.chunk_index)}
                              {matched ? (
                                <span className="ml-2 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-700">
                                  matched
                                </span>
                              ) : null}
                            </td>
                            <td className="max-w-[360px] py-3 text-[#44546f]">
                              {shortText(chunk.content)}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ) : null}

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-[12px] border border-[rgba(9,30,66,0.08)] bg-[#fafbfc] p-3">
              <h4 className="text-sm font-semibold text-[#172b4d]">
                Matched expected
              </h4>
              {item.matched_expected.length === 0 ? (
                <p className="mt-2 text-sm text-[#44546f]">
                  Совпадений с expected relevant нет.
                </p>
              ) : (
                <div className="mt-2 space-y-2">
                  {item.matched_expected.map((match, index) => (
                    <p
                      className="rounded-[10px] bg-white px-3 py-2 text-sm text-[#44546f]"
                      key={`${match.chunk_id ?? "match"}-${index}`}
                    >
                      rank {asString(match.rank)}
                      {" · "}chunk {asString(match.chunk_id)}
                      {" · "}text: {shortText(match.text_contains, 120)}
                    </p>
                  ))}
                </div>
              )}
            </div>
            <div className="rounded-[12px] border border-[rgba(9,30,66,0.08)] bg-[#fafbfc] p-3">
              <h4 className="text-sm font-semibold text-[#172b4d]">
                Judge result
              </h4>
              {Object.keys(judgePayload).length === 0 ? (
                <p className="mt-2 text-sm text-[#44546f]">
                  LLM judge не запускался или не вернул payload.
                </p>
              ) : (
                <div className="mt-2 space-y-2 text-sm text-[#44546f]">
                  <p>
                    groundedness:{" "}
                    <span className="font-semibold text-[#172b4d]">
                      {asString(judgePayload.groundedness)}
                    </span>
                  </p>
                  <p>
                    correctness:{" "}
                    <span className="font-semibold text-[#172b4d]">
                      {asString(judgePayload.correctness)}
                    </span>
                  </p>
                  {judgePayload.rationale ? (
                    <p className="rounded-[10px] bg-white px-3 py-2">
                      {asString(judgePayload.rationale)}
                    </p>
                  ) : null}
                  {unsupportedClaims.length ? (
                    <div className="rounded-[10px] bg-white px-3 py-2">
                      <p className="font-semibold text-[#172b4d]">
                        Unsupported claims
                      </p>
                      <ul className="mt-1 list-disc space-y-1 pl-5">
                        {unsupportedClaims.map((claim, index) => (
                          <li key={`${String(claim)}-${index}`}>
                            {String(claim)}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  {judgeRuns.length ? (
                    <div className="overflow-x-auto rounded-[10px] bg-white px-3 py-2">
                      <p className="font-semibold text-[#172b4d]">
                        Judge comparison
                      </p>
                      <table className="mt-2 w-full min-w-[560px] text-left text-xs">
                        <thead className="text-[#6b778c]">
                          <tr>
                            <th className="py-1">Provider</th>
                            <th className="py-1">Groundedness</th>
                            <th className="py-1">Correctness</th>
                            <th className="py-1">Rationale</th>
                          </tr>
                        </thead>
                        <tbody>
                          {judgeRuns.map((run) => {
                            const payload = asRecord(run.payload);
                            return (
                              <tr key={String(run.index)}>
                                <td className="py-1 pr-3 text-[#44546f]">
                                  {asString(run.provider_kind)} /{" "}
                                  {asString(run.model)}
                                </td>
                                <td className="py-1 pr-3">
                                  {asString(payload.groundedness)}
                                </td>
                                <td className="py-1 pr-3">
                                  {asString(payload.correctness)}
                                </td>
                                <td className="py-1">
                                  {shortText(payload.rationale, 120)}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  ) : null}
                </div>
              )}
            </div>
          </div>
        </div>
      </details>
    );
  }

  function renderResults() {
    if (!activeRun) {
      return (
        <div className="space-y-5">
          <p className="rounded-[16px] border border-dashed border-[rgba(9,30,66,0.16)] bg-white p-6 text-sm text-[#44546f]">
            Запустите эксперимент или откройте сохранённый запуск из истории.
          </p>
          {renderRunHistory()}
        </div>
      );
    }

    const metrics = activeRun.summary_metrics ?? {};
    return (
      <div className="space-y-5">
        <section className="rounded-[20px] border border-[rgba(9,30,66,0.12)] bg-white p-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="section-eyebrow">Run status</p>
              <h3 className="mt-2 text-2xl font-semibold text-[#172b4d]">
                {statusLabel(activeRun.status)}
              </h3>
              <p className="mt-2 text-sm text-[#44546f]">
                {activeRun.started_at
                  ? `Старт: ${formatDateTimeFull(activeRun.started_at)}`
                  : "Ожидает запуска"}
                {activeRun.latency_ms ? ` · ${activeRun.latency_ms} мс` : ""}
              </p>
              {activeRun.error_message ? (
                <p className="mt-3 rounded-[12px] bg-rose-50 px-4 py-3 text-sm text-rose-700">
                  {activeRun.error_message}
                </p>
              ) : null}
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
          {(
            [
              ["Recall@1", metrics.recall_at_1],
              ["Recall@3", metrics.recall_at_3],
              ["Recall@5", metrics.recall_at_5],
              ["MRR", metrics.mrr],
              ["BM25 Recall@5", metrics.bm25_recall_at_5],
              ["BM25 MRR", metrics.bm25_mrr],
              ["MRR delta", metrics.rag_vs_bm25_mrr_delta],
              ["No-context", metrics.no_context_rate],
              ["p95 retrieval", metrics.p95_retrieval_latency_ms],
              ["p95 indexing", metrics.p95_index_latency_ms],
              ["Tokens", metrics.total_tokens],
            ] as Array<[string, unknown]>
          ).map(([label, value]) => (
            <article
              key={label}
              className="rounded-[16px] border border-[rgba(9,30,66,0.12)] bg-white p-4"
            >
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[#6b778c]">
                {label}
              </p>
              <p className="mt-2 text-2xl font-semibold text-[#172b4d]">
                {metricValue(value)}
              </p>
            </article>
          ))}
        </section>

        <section className="rounded-[20px] border border-[rgba(9,30,66,0.12)] bg-white p-6">
          <h3 className="text-lg font-semibold text-[#172b4d]">Индексация</h3>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead className="text-xs uppercase tracking-[0.12em] text-[#6b778c]">
                <tr>
                  <th className="py-2">Task external id</th>
                  <th className="py-2">Status</th>
                  <th className="py-2">Chunks</th>
                  <th className="py-2">Chunking</th>
                  <th className="py-2">Qdrant write</th>
                  <th className="py-2">Total</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[rgba(9,30,66,0.08)]">
                {activeRun.index_results.map((item) => (
                  <tr key={item.id}>
                    <td className="py-3 font-medium text-[#172b4d]">
                      {item.task_external_id}
                    </td>
                    <td className="py-3 text-[#44546f]">{item.status}</td>
                    <td className="py-3 text-[#44546f]">{item.chunks_total}</td>
                    <td className="py-3 text-[#44546f]">
                      {metricValue(item.chunking_ms)}
                    </td>
                    <td className="py-3 text-[#44546f]">
                      {metricValue(item.embedding_and_qdrant_write_ms)}
                    </td>
                    <td className="py-3 text-[#44546f]">
                      {metricValue(item.total_index_ms)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {renderCaseFilters()}

        <section className="rounded-[20px] border border-[rgba(9,30,66,0.12)] bg-white p-6">
          <h3 className="text-lg font-semibold text-[#172b4d]">Кейсы</h3>
          <div className="mt-4 space-y-4">
            {visibleCaseResults.length === 0 ? (
              <p className="rounded-[14px] border border-dashed border-[rgba(9,30,66,0.16)] bg-[#fafbfc] p-4 text-sm text-[#44546f]">
                По текущим фильтрам кейсов нет.
              </p>
            ) : null}
            {visibleCaseResults.map((item) => (
              <article
                key={item.id}
                className="rounded-[16px] border border-[rgba(9,30,66,0.12)] bg-[#fafbfc] p-4"
              >
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <p className="font-semibold text-[#172b4d]">
                      {item.case_external_id}
                    </p>
                    <p className="mt-1 text-sm text-[#44546f]">
                      {item.question}
                    </p>
                  </div>
                  <p className="text-sm text-[#44546f]">
                    R@5: {metricValue(item.metrics.recall_at_5)}
                    {" · "}MRR: {metricValue(item.metrics.mrr)}
                    {item.metrics.bm25_mrr !== undefined ? (
                      <>
                        {" · "}BM25 R@5:{" "}
                        {metricValue(item.metrics.bm25_recall_at_5)}
                        {" · "}BM25 MRR: {metricValue(item.metrics.bm25_mrr)}
                      </>
                    ) : null}
                    {" · "}judge: {metricValue(item.metrics.correctness)}
                  </p>
                </div>
                {item.answer_text ? (
                  <p className="mt-3 whitespace-pre-wrap rounded-[12px] bg-white p-3 text-sm leading-6 text-[#172b4d]">
                    {item.answer_text}
                  </p>
                ) : null}
                {renderRetrievalDetails(item)}
              </article>
            ))}
          </div>
        </section>
      </div>
    );
  }

  if (loading) {
    return <LoadingSpinner label="Загрузка RAG Eval" />;
  }

  return (
    <section className="space-y-6">
      <header className="rounded-[20px] border border-[rgba(9,30,66,0.12)] bg-white p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="section-eyebrow">RAG Eval</p>
            <h2 className="mt-2 text-2xl font-semibold text-[#172b4d]">
              Оценка качества RAG
            </h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[#44546f]">
              Импортируйте eval-набор, запускайте retrieval/QA/judge
              конфигурации и экспортируйте метрики для исследовательской части.
            </p>
          </div>
          <nav className="flex flex-wrap gap-2" aria-label="RAG Eval">
            {TABS.map((tab) => (
              <button
                key={tab.key}
                className={
                  activeTab === tab.key
                    ? "ui-button-primary"
                    : "ui-button-secondary"
                }
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
        <p className="rounded-[14px] bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p className="rounded-[14px] bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          {notice}
        </p>
      ) : null}

      {activeTab === "import" ? renderImport() : null}
      {activeTab === "datasets" ? renderDatasets() : null}
      {activeTab === "run" ? renderRun() : null}
      {activeTab === "results" ? renderResults() : null}

      <ConfirmDialog
        busy={deletingRunId === runPendingDeletion?.id}
        confirmLabel="Удалить запуск"
        description={
          runPendingDeletion
            ? `Удалить сохранённый RAG Eval запуск от ${formatDateTimeFull(
                runPendingDeletion.created_at,
              )}? Набор данных останется доступен для новых прогонов.`
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
