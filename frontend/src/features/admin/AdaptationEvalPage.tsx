import { useEffect, useMemo, useState } from "react";

import {
  adminApi,
  type AdaptationEvalCaseResultRead,
  type AdaptationEvalDatasetDetailRead,
  type AdaptationEvalDatasetRead,
  type AdaptationEvalExportArtifact,
  type AdaptationEvalImportPayload,
  type AdaptationEvalRunConfig,
  type AdaptationEvalRunPageRead,
  type AdaptationEvalRunRead,
} from "@/api/adminApi";
import { projectsApi, type ProjectRead } from "@/api/projectsApi";
import { LoadingSpinner } from "@/shared/components/LoadingSpinner";
import { getApiErrorMessage } from "@/shared/lib/apiError";
import { formatDateTimeFull } from "@/shared/lib/locale";

type AdaptationEvalTab = "import" | "datasets" | "run" | "results";
type ExportFormat = "json" | "csv";

const TABS: Array<{ key: AdaptationEvalTab; label: string }> = [
  { key: "import", label: "Импорт" },
  { key: "datasets", label: "Наборы" },
  { key: "run", label: "Запуск" },
  { key: "results", label: "Результаты" },
];

const DEFAULT_CONFIG: AdaptationEvalRunConfig = {
  cleanup_synthetic_tasks: true,
  quality_gates: {
    capture_recall_min: 0.95,
    context_issue_f1_min: 0.7,
    context_question_f1_min: 0.75,
    duplicate_rate_max: 0.1,
    retrieval_recall_at_k_min: 0.8,
  },
  retrieval_limit: 5,
};

const JSON_TEMPLATE = `{
  "dataset_name": "Adaptation eval set",
  "project_id": "project-id",
  "cases": [
    {
      "external_id": "adapt-auth-roles-positive",
      "scenario_type": "positive",
      "historical_tasks": [
        {
          "title": "Авторизация по email",
          "content": "Нужно описать вход пользователя по email и паролю.",
          "tags": ["auth"],
          "chat_messages": [
            "Какие роли пользователей должны поддерживаться?"
          ]
        }
      ],
      "probe_task": {
        "title": "Вход в личный кабинет",
        "content": "Нужно реализовать вход по email и паролю.",
        "tags": ["auth"],
        "custom_rules": [],
        "related_tasks": [],
        "attachment_names": []
      },
      "expected_captured_questions": [
        "Какие роли пользователей должны поддерживаться?"
      ],
      "expected_retrieved_questions": [
        "Какие роли пользователей должны поддерживаться?"
      ],
      "expected_context_questions": [
        "Какие роли пользователей должны поддерживаться?"
      ],
      "expected_verdict": "needs_rework",
      "expected_context_issues": [
        {
          "code": "context_question",
          "severity": "medium",
          "message": "Какие роли пользователей должны поддерживаться?",
          "source": "context_questions"
        }
      ],
      "metadata": {
        "scenario": "chat_to_qdrant_to_validation"
      }
    },
    {
      "external_id": "adapt-avatar-negative",
      "scenario_type": "negative_control",
      "historical_tasks": [
        {
          "title": "Авторизация по email",
          "content": "Нужно описать вход пользователя по email и паролю.",
          "tags": ["auth"],
          "chat_messages": [
            "Какие роли пользователей должны поддерживаться?"
          ]
        }
      ],
      "probe_task": {
        "title": "Загрузка аватара",
        "content": "Пользователь может загрузить изображение профиля.",
        "tags": ["profile"],
        "custom_rules": [],
        "related_tasks": [],
        "attachment_names": []
      },
      "expected_captured_questions": [
        "Какие роли пользователей должны поддерживаться?"
      ],
      "expected_retrieved_questions": [],
      "expected_context_questions": [],
      "expected_verdict": "approved",
      "expected_context_issues": [],
      "metadata": {
        "scenario": "negative_control"
      }
    }
  ]
}`;

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
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

function shortText(value: unknown, maxLength = 180) {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  return text.length <= maxLength ? text : `${text.slice(0, maxLength - 1)}…`;
}

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

function downloadText(filename: string, content: string) {
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export default function AdaptationEvalPage() {
  const [activeTab, setActiveTab] = useState<AdaptationEvalTab>("import");
  const [projects, setProjects] = useState<ProjectRead[]>([]);
  const [datasets, setDatasets] = useState<AdaptationEvalDatasetRead[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [selectedDatasetId, setSelectedDatasetId] = useState("");
  const [datasetDetail, setDatasetDetail] =
    useState<AdaptationEvalDatasetDetailRead | null>(null);
  const [runHistory, setRunHistory] =
    useState<AdaptationEvalRunPageRead | null>(null);
  const [activeRun, setActiveRun] = useState<AdaptationEvalRunRead | null>(
    null,
  );
  const [importContent, setImportContent] = useState(JSON_TEMPLATE);
  const [config, setConfig] = useState<AdaptationEvalRunConfig>(DEFAULT_CONFIG);
  const [exportArtifact, setExportArtifact] =
    useState<AdaptationEvalExportArtifact>("case_results");
  const [exportFormat, setExportFormat] = useState<ExportFormat>("csv");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectedDataset = useMemo(
    () => datasets.find((dataset) => dataset.id === selectedDatasetId) ?? null,
    [datasets, selectedDatasetId],
  );

  useEffect(() => {
    async function loadInitial() {
      try {
        setLoading(true);
        const [loadedProjects, loadedDatasets] = await Promise.all([
          projectsApi.list(),
          adminApi.listAdaptationEvalDatasets(),
        ]);
        setProjects(loadedProjects);
        setDatasets(loadedDatasets);
        const projectId = loadedProjects[0]?.id ?? "";
        const datasetId = loadedDatasets[0]?.id ?? "";
        setSelectedProjectId(projectId);
        setSelectedDatasetId(datasetId);
        if (datasetId) {
          const [detail, history] = await Promise.all([
            adminApi.getAdaptationEvalDataset(datasetId),
            adminApi.listAdaptationEvalRuns(datasetId, { page: 1, size: 10 }),
          ]);
          setDatasetDetail(detail);
          setRunHistory(history);
        }
      } catch (caught) {
        setError(
          getApiErrorMessage(
            caught,
            "Не удалось загрузить Adaptation Eval.",
          ),
        );
      } finally {
        setLoading(false);
      }
    }
    void loadInitial();
  }, []);

  async function reloadDatasets(nextDatasetId = selectedDatasetId) {
    const loaded = await adminApi.listAdaptationEvalDatasets();
    setDatasets(loaded);
    if (nextDatasetId) {
      setSelectedDatasetId(nextDatasetId);
    }
  }

  async function loadDataset(datasetId: string) {
    const [detail, history] = await Promise.all([
      adminApi.getAdaptationEvalDataset(datasetId),
      adminApi.listAdaptationEvalRuns(datasetId, { page: 1, size: 10 }),
    ]);
    setDatasetDetail(detail);
    setRunHistory(history);
  }

  async function handleImport(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      setBusy(true);
      setError(null);
      setNotice(null);
      const parsed = JSON.parse(importContent) as AdaptationEvalImportPayload;
      const payload = {
        ...parsed,
        project_id: selectedProjectId || parsed.project_id,
      };
      const result = await adminApi.importAdaptationEvalDataset(payload);
      await reloadDatasets(result.dataset.id);
      setDatasetDetail(result.dataset);
      setSelectedDatasetId(result.dataset.id);
      setNotice(`Импортировано кейсов: ${result.imported_cases}.`);
      setActiveTab("datasets");
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось импортировать набор."));
    } finally {
      setBusy(false);
    }
  }

  async function handleRun() {
    if (!selectedDatasetId) {
      setError("Выберите набор перед запуском.");
      return;
    }
    try {
      setBusy(true);
      setError(null);
      setNotice(null);
      const run = await adminApi.createAdaptationEvalRun(
        selectedDatasetId,
        config,
      );
      const detail = await adminApi.getAdaptationEvalRun(run.id);
      setActiveRun(detail);
      await loadDataset(selectedDatasetId);
      await reloadDatasets(selectedDatasetId);
      setNotice("Adaptation Eval запущен.");
      setActiveTab("results");
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось запустить eval."));
    } finally {
      setBusy(false);
    }
  }

  async function openRun(runId: string) {
    try {
      setBusy(true);
      setError(null);
      const detail = await adminApi.getAdaptationEvalRun(runId);
      setActiveRun(detail);
      setActiveTab("results");
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось открыть запуск."));
    } finally {
      setBusy(false);
    }
  }

  async function handleExport() {
    if (!activeRun) {
      return;
    }
    try {
      setBusy(true);
      setError(null);
      const content = await adminApi.exportAdaptationEvalRun(
        activeRun.id,
        exportArtifact,
        exportFormat,
      );
      downloadText(
        `adaptation-eval-${exportArtifact}-${activeRun.id}.${exportFormat}`,
        content,
      );
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось экспортировать запуск."));
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <LoadingSpinner label="Загрузка Adaptation Eval" />;
  }

  return (
    <div className="space-y-6">
      <section className="page-panel p-5">
        <p className="section-eyebrow">Adaptation Eval</p>
        <h2 className="mt-2 text-2xl font-semibold text-[#172b4d]">
          Проверка адаптации валидатора
        </h2>
        <p className="mt-2 max-w-4xl text-sm text-[#626f86]">
          Инструмент прогоняет полный real-контур: вопрос в чате, сохранение в
          базе вопросов, поиск в Qdrant и применение context questions при
          валидации новой задачи.
        </p>
        <div className="mt-5 flex flex-wrap gap-2">
          {TABS.map((tab) => (
            <button
              className={
                activeTab === tab.key ? "ui-button-primary" : "ui-button-secondary"
              }
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              type="button"
            >
              {tab.label}
            </button>
          ))}
        </div>
      </section>

      {notice ? (
        <div className="rounded-[10px] border border-[#baf3db] bg-[#effcf6] px-4 py-3 text-sm text-[#216e4e]">
          {notice}
        </div>
      ) : null}
      {error ? (
        <div className="rounded-[10px] border border-[#ffd5d2] bg-[#fff2f0] px-4 py-3 text-sm text-[#ae2e24]">
          {error}
        </div>
      ) : null}

      {activeTab === "import" ? renderImport() : null}
      {activeTab === "datasets" ? renderDatasets() : null}
      {activeTab === "run" ? renderRun() : null}
      {activeTab === "results" ? renderResults() : null}
    </div>
  );

  function renderImport() {
    return (
      <form className="page-panel space-y-5 p-5" onSubmit={handleImport}>
        <div className="grid gap-4 md:grid-cols-[1fr_auto] md:items-end">
          <label className="block">
            <span className="mb-2 block text-sm font-semibold text-[#44546f]">
              Проект
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
          <button
            className="ui-button-secondary"
            onClick={() => setImportContent(JSON_TEMPLATE)}
            type="button"
          >
            Вернуть шаблон
          </button>
        </div>
        <label className="block">
          <span className="mb-2 block text-sm font-semibold text-[#44546f]">
            JSON dataset
          </span>
          <textarea
            className="ui-field min-h-[520px] resize-y font-mono text-xs leading-6"
            onChange={(event) => setImportContent(event.target.value)}
            spellCheck={false}
            value={importContent}
          />
        </label>
        <button className="ui-button-primary" disabled={busy} type="submit">
          {busy ? "Импортируем..." : "Импортировать набор"}
        </button>
      </form>
    );
  }

  function renderDatasets() {
    return (
      <section className="page-panel overflow-hidden">
        <div className="flex flex-col gap-3 border-b border-[rgba(9,30,66,0.1)] p-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="section-eyebrow">Datasets</p>
            <h3 className="mt-2 text-xl font-semibold text-[#172b4d]">
              Наборы Adaptation Eval
            </h3>
          </div>
          <button
            className="ui-button-secondary"
            onClick={() => void reloadDatasets(selectedDatasetId)}
            type="button"
          >
            Обновить
          </button>
        </div>
        {datasets.length === 0 ? (
          <p className="p-5 text-sm text-[#626f86]">Наборов пока нет.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] text-left text-sm">
              <thead className="bg-[#fafbfc] text-xs uppercase tracking-[0.12em] text-[#626f86]">
                <tr>
                  <th className="px-4 py-3">Dataset</th>
                  <th className="px-4 py-3">Проект</th>
                  <th className="px-4 py-3">Cases</th>
                  <th className="px-4 py-3">Last run</th>
                  <th className="px-4 py-3">Updated</th>
                  <th className="px-4 py-3 text-right">Действия</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[rgba(9,30,66,0.08)]">
                {datasets.map((dataset) => (
                  <tr
                    className={
                      dataset.id === selectedDatasetId ? "bg-[#f4f8ff]" : "bg-white"
                    }
                    key={dataset.id}
                  >
                    <td className="px-4 py-4">
                      <p className="font-semibold text-[#172b4d]">
                        {dataset.name}
                      </p>
                      <p className="mt-1 text-xs text-[#626f86]">{dataset.id}</p>
                    </td>
                    <td className="px-4 py-4 text-[#44546f]">
                      {dataset.project_name ?? dataset.project_id}
                    </td>
                    <td className="px-4 py-4 text-[#44546f]">
                      {dataset.cases_total}
                    </td>
                    <td className="px-4 py-4 text-[#44546f]">
                      {statusLabel(dataset.last_run_status)}
                    </td>
                    <td className="px-4 py-4 text-[#44546f]">
                      {formatDateTimeFull(dataset.updated_at)}
                    </td>
                    <td className="px-4 py-4">
                      <div className="flex justify-end gap-2">
                        <button
                          className="ui-button-secondary"
                          onClick={() => {
                            setSelectedDatasetId(dataset.id);
                            void loadDataset(dataset.id);
                          }}
                          type="button"
                        >
                          Открыть
                        </button>
                        <button
                          className="ui-button-primary"
                          onClick={() => {
                            setSelectedDatasetId(dataset.id);
                            void loadDataset(dataset.id);
                            setActiveTab("run");
                          }}
                          type="button"
                        >
                          Запуск
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {datasetDetail ? (
          <div className="border-t border-[rgba(9,30,66,0.08)] p-5">
            <h4 className="text-base font-semibold text-[#172b4d]">
              Кейсы: {datasetDetail.name}
            </h4>
            <div className="mt-4 grid gap-3 lg:grid-cols-2">
              {datasetDetail.cases.map((caseItem) => (
                <article
                  className="rounded-[8px] border border-[rgba(9,30,66,0.1)] bg-white p-4"
                  key={caseItem.id}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-semibold text-[#172b4d]">
                        {caseItem.external_id}
                      </p>
                      <p className="mt-1 text-xs uppercase tracking-[0.12em] text-[#626f86]">
                        {caseItem.scenario_type}
                      </p>
                    </div>
                    <span className="rounded-[999px] bg-[#f4f5f7] px-3 py-1 text-xs text-[#44546f]">
                      {caseItem.expected_verdict}
                    </span>
                  </div>
                  <p className="mt-3 text-sm text-[#44546f]">
                    {shortText(asRecord(caseItem.probe_task).title)}
                  </p>
                  <p className="mt-3 text-xs text-[#626f86]">
                    expected captured: {caseItem.expected_captured_questions.length}
                    {" · "}retrieved: {caseItem.expected_retrieved_questions.length}
                    {" · "}context: {caseItem.expected_context_questions.length}
                  </p>
                </article>
              ))}
            </div>
          </div>
        ) : null}
      </section>
    );
  }

  function renderRun() {
    return (
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(360px,440px)]">
        <section className="page-panel p-5">
          <p className="section-eyebrow">Run config</p>
          <h3 className="mt-2 text-xl font-semibold text-[#172b4d]">
            {selectedDataset?.name ?? "Набор не выбран"}
          </h3>
          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-[#44546f]">
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
            <label className="flex items-center gap-3 pt-8 text-sm font-semibold text-[#44546f]">
              <input
                checked={config.cleanup_synthetic_tasks}
                onChange={(event) =>
                  setConfig((current) => ({
                    ...current,
                    cleanup_synthetic_tasks: event.target.checked,
                  }))
                }
                type="checkbox"
              />
              Удалять synthetic tasks после run
            </label>
          </div>
          <button
            className="ui-button-primary mt-5"
            disabled={busy || !selectedDatasetId}
            onClick={() => void handleRun()}
            type="button"
          >
            {busy ? "Запускаем..." : "Запустить Adaptation Eval"}
          </button>
        </section>

        <section className="page-panel overflow-hidden">
          <div className="border-b border-[rgba(9,30,66,0.1)] p-5">
            <p className="section-eyebrow">History</p>
            <h3 className="mt-2 text-xl font-semibold text-[#172b4d]">
              История запусков
            </h3>
          </div>
          {(runHistory?.items ?? []).length === 0 ? (
            <p className="p-5 text-sm text-[#626f86]">Запусков пока нет.</p>
          ) : (
            <div className="divide-y divide-[rgba(9,30,66,0.08)]">
              {runHistory?.items.map((run) => (
                <div className="flex items-center justify-between gap-3 p-4" key={run.id}>
                  <div>
                    <p className="font-semibold text-[#172b4d]">
                      {statusLabel(run.status)}
                    </p>
                    <p className="mt-1 text-xs text-[#626f86]">
                      {formatDateTimeFull(run.created_at)}
                    </p>
                  </div>
                  <button
                    className="ui-button-secondary"
                    onClick={() => void openRun(run.id)}
                    type="button"
                  >
                    Открыть
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    );
  }

  function renderResults() {
    if (!activeRun) {
      return (
        <p className="page-panel p-5 text-sm text-[#626f86]">
          Откройте запуск из истории или запустите новый eval.
        </p>
      );
    }
    const summary = asRecord(activeRun.summary_metrics);
    const gates = asArray(summary.quality_gates).map(asRecord);
    return (
      <div className="space-y-6">
        <section className="grid gap-4 md:grid-cols-4">
          <MetricTile label="Status" value={statusLabel(activeRun.status)} />
          <MetricTile label="Gate status" value={metricValue(summary.gate_status)} />
          <MetricTile label="Cases" value={metricValue(summary.cases_total)} />
          <MetricTile label="Pass rate" value={metricValue(summary.pass_rate)} />
        </section>

        <section className="page-panel overflow-hidden">
          <div className="border-b border-[rgba(9,30,66,0.1)] p-5">
            <p className="section-eyebrow">Quality gates</p>
            <h3 className="mt-2 text-xl font-semibold text-[#172b4d]">
              Пороговые метрики адаптации
            </h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className="bg-[#fafbfc] text-xs uppercase tracking-[0.12em] text-[#626f86]">
                <tr>
                  <th className="px-4 py-3">Gate</th>
                  <th className="px-4 py-3">Value</th>
                  <th className="px-4 py-3">Threshold</th>
                  <th className="px-4 py-3">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[rgba(9,30,66,0.08)]">
                {gates.map((gate) => (
                  <tr key={String(gate.key)}>
                    <td className="px-4 py-4 font-semibold text-[#172b4d]">
                      {metricValue(gate.label)}
                    </td>
                    <td className="px-4 py-4 text-[#44546f]">
                      {metricValue(gate.value)}
                    </td>
                    <td className="px-4 py-4 text-[#44546f]">
                      {metricValue(gate.threshold)}
                    </td>
                    <td className="px-4 py-4 text-[#44546f]">
                      {gate.passed ? "passed" : "failed"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="page-panel p-5">
          <div className="grid gap-3 sm:grid-cols-[1fr_160px_160px_auto] sm:items-end">
            <div>
              <p className="section-eyebrow">Export</p>
              <h3 className="mt-2 text-lg font-semibold text-[#172b4d]">
                Выгрузка отчета
              </h3>
            </div>
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-[#44546f]">
                Artifact
              </span>
              <select
                aria-label="Export artifact"
                className="ui-field"
                onChange={(event) =>
                  setExportArtifact(
                    event.target.value as AdaptationEvalExportArtifact,
                  )
                }
                value={exportArtifact}
              >
                <option value="case_results">Case results</option>
                <option value="metrics">Metrics</option>
              </select>
            </label>
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-[#44546f]">
                Format
              </span>
              <select
                aria-label="Export format"
                className="ui-field"
                onChange={(event) =>
                  setExportFormat(event.target.value as ExportFormat)
                }
                value={exportFormat}
              >
                <option value="csv">CSV</option>
                <option value="json">JSON</option>
              </select>
            </label>
            <div className="flex flex-wrap gap-2">
              <button
                className="ui-button-secondary"
                onClick={() => void openRun(activeRun.id)}
                type="button"
              >
                Обновить
              </button>
              <button
                className="ui-button-secondary"
                onClick={() => void handleExport()}
                type="button"
              >
                Export
              </button>
            </div>
          </div>
        </section>

        <div className="space-y-4">
          {activeRun.case_results.map((item) => (
            <CaseResultCard item={item} key={item.id} />
          ))}
        </div>
      </div>
    );
  }
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="page-panel p-4">
      <p className="section-eyebrow">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-[#172b4d]">{value}</p>
    </div>
  );
}

function CaseResultCard({ item }: { item: AdaptationEvalCaseResultRead }) {
  const actual = asRecord(item.actual_result);
  const metrics = asRecord(item.metrics);
  const contextValidation = asRecord(
    actual.context_validation ?? actual.full_validation,
  );
  const retrieval = asArray(actual.retrieval_results).map(asRecord);
  return (
    <article className="page-panel overflow-hidden">
      <div className="flex flex-col gap-3 border-b border-[rgba(9,30,66,0.1)] p-5 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="section-eyebrow">{item.scenario_type}</p>
          <h3 className="mt-2 text-lg font-semibold text-[#172b4d]">
            {item.case_external_id}
          </h3>
        </div>
        <span className="rounded-[999px] bg-[#f4f5f7] px-3 py-1 text-sm font-semibold text-[#44546f]">
          {statusLabel(item.status)}
        </span>
      </div>

      <div className="grid gap-4 p-5 lg:grid-cols-3">
        <StageBlock
          label="Capture"
          metric={metricValue(metrics.capture_recall)}
          values={asArray(actual.captured_questions)}
        />
        <StageBlock
          label="Retrieval"
          metric={metricValue(metrics.retrieval_recall_at_k)}
          values={retrieval.map((row) => `${row.rank}. ${row.question_text}`)}
        />
        <StageBlock
          label="Context validation"
          metric={metricValue(metrics.context_question_f1)}
          values={asArray(contextValidation.context_questions)}
        />
      </div>

      <div className="border-t border-[rgba(9,30,66,0.08)] p-5">
        <div className="grid gap-3 md:grid-cols-2">
          <MetricMini
            label="Context issue F1"
            value={metricValue(metrics.context_issue_f1)}
          />
          <MetricMini
            label="Duplicate rate"
            value={metricValue(metrics.overall_question_duplicate_rate)}
          />
        </div>
        {item.error_message ? (
          <p className="mt-4 rounded-[8px] bg-[#fff2f0] p-3 text-sm text-[#ae2e24]">
            {item.error_message}
          </p>
        ) : null}
      </div>
    </article>
  );
}

function StageBlock({
  label,
  metric,
  values,
}: {
  label: string;
  metric: string;
  values: unknown[];
}) {
  return (
    <div className="rounded-[8px] border border-[rgba(9,30,66,0.1)] bg-white p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-semibold text-[#172b4d]">{label}</p>
        <span className="text-sm text-[#626f86]">{metric}</span>
      </div>
      {values.length ? (
        <ul className="mt-3 space-y-2 text-sm text-[#44546f]">
          {values.slice(0, 4).map((value, index) => (
            <li key={`${label}-${index}`}>{shortText(value, 110)}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm text-[#626f86]">Нет данных.</p>
      )}
    </div>
  );
}

function MetricMini({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[8px] border border-[rgba(9,30,66,0.1)] bg-[#fafbfc] p-3">
      <p className="text-xs uppercase tracking-[0.12em] text-[#626f86]">
        {label}
      </p>
      <p className="mt-1 text-lg font-semibold text-[#172b4d]">{value}</p>
    </div>
  );
}
