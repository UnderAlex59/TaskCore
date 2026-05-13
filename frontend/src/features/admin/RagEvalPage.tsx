import { useEffect, useMemo, useState } from "react";

import {
  adminApi,
  type RagEvalDatasetDetailRead,
  type RagEvalDatasetRead,
  type RagEvalImportFormat,
  type RagEvalIndexingMode,
  type RagEvalRunConfig,
  type RagEvalRunRead,
} from "@/api/adminApi";
import { projectsApi, type ProjectRead } from "@/api/projectsApi";
import { LoadingSpinner } from "@/shared/components/LoadingSpinner";
import { getApiErrorMessage } from "@/shared/lib/apiError";
import { formatDateTimeFull } from "@/shared/lib/locale";

type RagEvalTab = "import" | "datasets" | "run" | "results";

const TABS: Array<{ key: RagEvalTab; label: string }> = [
  { key: "import", label: "Импорт" },
  { key: "datasets", label: "Наборы" },
  { key: "run", label: "Запуск" },
  { key: "results", label: "Результаты" },
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
  min_score_override: null,
};

type RagEvalBooleanConfigKey =
  | "use_query_rewriter"
  | "use_hybrid_rerank"
  | "include_cross_task"
  | "include_current_task_content"
  | "run_answer_agent"
  | "run_llm_judge";

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
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [importFormat, setImportFormat] = useState<RagEvalImportFormat>("json");
  const [importName, setImportName] = useState("RAG eval set");
  const [importContent, setImportContent] = useState(JSON_TEMPLATE);
  const [config, setConfig] = useState<RagEvalRunConfig>(DEFAULT_CONFIG);

  async function loadBootstrap() {
    try {
      setLoading(true);
      setError(null);
      const [projectList, datasetList] = await Promise.all([
        projectsApi.list(),
        adminApi.listRagEvalDatasets(),
      ]);
      setProjects(projectList);
      setDatasets(datasetList);
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
      setError(getApiErrorMessage(caught, "Не удалось загрузить набор RAG Eval."));
    }
  }

  useEffect(() => {
    void loadBootstrap();
  }, []);

  useEffect(() => {
    void loadDataset(selectedDatasetId);
  }, [selectedDatasetId]);

  useEffect(() => {
    if (!activeRun || !["queued", "running"].includes(activeRun.status)) {
      return;
    }
    const timer = window.setInterval(() => {
      void adminApi.getRagEvalRun(activeRun.id).then(setActiveRun).catch(() => {});
    }, 2000);
    return () => window.clearInterval(timer);
  }, [activeRun]);

  const selectedDataset = useMemo(
    () => datasets.find((item) => item.id === selectedDatasetId) ?? null,
    [datasets, selectedDatasetId],
  );

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
    try {
      setBusy(true);
      setError(null);
      const run = await adminApi.createRagEvalRun(selectedDatasetId, config);
      const runDetail = await adminApi.getRagEvalRun(run.id);
      setActiveRun(runDetail);
      setActiveTab("results");
      setDatasets(await adminApi.listRagEvalDatasets());
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось запустить RAG Eval."));
    } finally {
      setBusy(false);
    }
  }

  async function handleExport(format: "json" | "csv") {
    if (!activeRun) {
      return;
    }
    const content = await adminApi.exportRagEvalRun(activeRun.id, format);
    downloadText(
      `rag-eval-${activeRun.id}.${format}`,
      content,
      format === "json" ? "application/json;charset=utf-8" : "text/csv;charset=utf-8",
    );
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
              onChange={(event) => setImportFormat(event.target.value as RagEvalImportFormat)}
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
                  {" · "}последний запуск: {statusLabel(dataset.last_run_status)}
                </p>
              </div>
              <button
                className={
                  selectedDatasetId === dataset.id
                    ? "ui-button-primary"
                    : "ui-button-secondary"
                }
                onClick={() => {
                  setSelectedDatasetId(dataset.id);
                  setActiveTab("run");
                }}
                type="button"
              >
                Выбрать
              </button>
            </div>
          </article>
        ))}
      </div>
    );
  }

  function renderRun() {
    return (
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
                  }))
                }
                type="checkbox"
              />
            </label>
          ))}
        </div>

        {datasetDetail ? (
          <p className="mt-5 text-sm text-[#44546f]">
            Выбран набор: {datasetDetail.name}. Задач: {datasetDetail.tasks_total},
            кейсов: {datasetDetail.cases_total}.
          </p>
        ) : selectedDataset ? (
          <p className="mt-5 text-sm text-[#44546f]">
            Выбран набор: {selectedDataset.name}.
          </p>
        ) : null}

        <button
          className="mt-5 ui-button-primary"
          disabled={busy || !selectedDatasetId}
          type="submit"
        >
          {busy ? "Запуск..." : "Запустить RAG Eval"}
        </button>
      </form>
    );
  }

  function renderResults() {
    if (!activeRun) {
      return (
        <p className="rounded-[16px] border border-dashed border-[rgba(9,30,66,0.16)] bg-white p-6 text-sm text-[#44546f]">
          Запустите эксперимент или выберите последний запуск из набора.
        </p>
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

        <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {([
            ["Recall@1", metrics.recall_at_1],
            ["Recall@3", metrics.recall_at_3],
            ["Recall@5", metrics.recall_at_5],
            ["MRR", metrics.mrr],
            ["No-context", metrics.no_context_rate],
            ["p95 retrieval", metrics.p95_retrieval_latency_ms],
            ["p95 indexing", metrics.p95_index_latency_ms],
            ["Tokens", metrics.total_tokens],
          ] as Array<[string, unknown]>).map(([label, value]) => (
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

        <section className="rounded-[20px] border border-[rgba(9,30,66,0.12)] bg-white p-6">
          <h3 className="text-lg font-semibold text-[#172b4d]">Кейсы</h3>
          <div className="mt-4 space-y-4">
            {activeRun.case_results.map((item) => (
              <article
                key={item.id}
                className="rounded-[16px] border border-[rgba(9,30,66,0.12)] bg-[#fafbfc] p-4"
              >
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <p className="font-semibold text-[#172b4d]">
                      {item.case_external_id}
                    </p>
                    <p className="mt-1 text-sm text-[#44546f]">{item.question}</p>
                  </div>
                  <p className="text-sm text-[#44546f]">
                    R@5: {metricValue(item.metrics.recall_at_5)}
                    {" · "}MRR: {metricValue(item.metrics.mrr)}
                    {" · "}judge: {metricValue(item.metrics.correctness)}
                  </p>
                </div>
                {item.answer_text ? (
                  <p className="mt-3 whitespace-pre-wrap rounded-[12px] bg-white p-3 text-sm leading-6 text-[#172b4d]">
                    {item.answer_text}
                  </p>
                ) : null}
                <details className="mt-3">
                  <summary className="cursor-pointer text-sm font-medium text-[#0c66e4]">
                    Retrieval details
                  </summary>
                  <pre className="mt-3 whitespace-pre-wrap break-words rounded-[12px] bg-white p-3 font-mono text-xs leading-5 text-[#44546f]">
                    {JSON.stringify(
                      {
                        matched_expected: item.matched_expected,
                        retrieved_chunks: item.retrieved_chunks,
                        judge_payload: item.judge_payload,
                      },
                      null,
                      2,
                    )}
                  </pre>
                </details>
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
              Импортируйте eval-набор, запускайте retrieval/QA/judge конфигурации
              и экспортируйте метрики для исследовательской части.
            </p>
          </div>
          <nav className="flex flex-wrap gap-2" aria-label="RAG Eval">
            {TABS.map((tab) => (
              <button
                key={tab.key}
                className={
                  activeTab === tab.key ? "ui-button-primary" : "ui-button-secondary"
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
    </section>
  );
}
