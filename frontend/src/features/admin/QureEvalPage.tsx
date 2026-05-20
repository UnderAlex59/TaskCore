import { useCallback, useEffect, useMemo, useState } from "react";

import {
  adminApi,
  type QureEvalCaseResultRead,
  type QureEvalRunListItemRead,
  type QureEvalRunRead,
} from "@/api/adminApi";
import { projectsApi, type ProjectRead } from "@/api/projectsApi";
import { LoadingSpinner } from "@/shared/components/LoadingSpinner";
import { getApiErrorMessage } from "@/shared/lib/apiError";
import { formatDateTimeFull } from "@/shared/lib/locale";

function statusLabel(status: string) {
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
      return "Пройден";
    case "failed":
      return "Не пройден";
    default:
      return status;
  }
}

function metricValue(value: unknown) {
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(4);
  }
  if (typeof value === "boolean") {
    return value ? "Да" : "Нет";
  }
  if (value === null || value === undefined || value === "") {
    return "н/д";
  }
  return String(value);
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function compactJson(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2);
}

function shortText(value: unknown, limit = 120) {
  const text = String(value ?? "").trim();
  if (text.length <= limit) {
    return text;
  }
  return `${text.slice(0, limit - 1)}…`;
}

function actualVerdict(item: QureEvalCaseResultRead) {
  return metricValue(item.actual_result.verdict);
}

function judgePassed(item: QureEvalCaseResultRead) {
  const payload = asRecord(item.judge_payload);
  return payload.passed ?? payload.match;
}

function judgeScore(item: QureEvalCaseResultRead) {
  return asRecord(item.judge_payload).score;
}

function judgeRationale(item: QureEvalCaseResultRead) {
  return asRecord(item.judge_payload).rationale;
}

function downloadText(filename: string, content: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export default function QureEvalPage() {
  const [projects, setProjects] = useState<ProjectRead[]>([]);
  const [runs, setRuns] = useState<QureEvalRunListItemRead[]>([]);
  const [activeRun, setActiveRun] = useState<QureEvalRunRead | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [selectedRunId, setSelectedRunId] = useState("");
  const [rowLimit, setRowLimit] = useState("100");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [deletingRunId, setDeletingRunId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const summary = useMemo(
    () => asRecord(activeRun?.summary_metrics),
    [activeRun?.summary_metrics],
  );
  const metricCards: Array<[string, unknown]> = [
    ["Judge pass rate", summary.judge_pass_rate],
    ["Verdict accuracy", summary.verdict_accuracy],
    ["Verdict F1", summary.verdict_f1],
    ["Weak-word F1", summary.weak_word_f1],
    ["Ошибки judge", summary.judge_errors],
  ];

  const canSubmit =
    Boolean(file) &&
    Boolean(selectedProjectId) &&
    Number.isInteger(Number(rowLimit)) &&
    Number(rowLimit) > 0 &&
    !submitting;

  const loadRuns = useCallback(async (preferredRunId = selectedRunId) => {
    const page = await adminApi.listQureEvalRuns({ page: 1, size: 20 });
    setRuns(page.items);
    const nextRunId =
      preferredRunId && page.items.some((run) => run.id === preferredRunId)
        ? preferredRunId
        : page.items[0]?.id ?? "";
    setSelectedRunId(nextRunId);
    return nextRunId;
  }, [selectedRunId]);

  const loadRun = useCallback(async (runId = selectedRunId) => {
    if (!runId) {
      setActiveRun(null);
      return;
    }
    setActiveRun(await adminApi.getQureEvalRun(runId));
  }, [selectedRunId]);

  useEffect(() => {
    async function loadInitialData() {
      setLoading(true);
      setError(null);
      try {
        const [loadedProjects, loadedRuns] = await Promise.all([
          projectsApi.list(),
          adminApi.listQureEvalRuns({ page: 1, size: 20 }),
        ]);
        setProjects(loadedProjects);
        setSelectedProjectId(loadedProjects[0]?.id ?? "");
        setRuns(loadedRuns.items);
        const firstRunId = loadedRuns.items[0]?.id ?? "";
        setSelectedRunId(firstRunId);
        if (firstRunId) {
          setActiveRun(await adminApi.getQureEvalRun(firstRunId));
        }
      } catch (caught) {
        setError(getApiErrorMessage(caught, "Не удалось загрузить QuRE Eval."));
      } finally {
        setLoading(false);
      }
    }
    void loadInitialData();
  }, []);

  useEffect(() => {
    if (!activeRun || !["queued", "running"].includes(activeRun.status)) {
      return;
    }
    const timer = window.setInterval(() => {
      void loadRuns(activeRun.id).then((runId) => {
        if (runId) {
          void loadRun(runId);
        }
      });
    }, 2000);
    return () => window.clearInterval(timer);
  }, [activeRun, loadRun, loadRuns]);

  async function handleCreateRun() {
    if (!file || !canSubmit) {
      return;
    }
    setSubmitting(true);
    setError(null);
    setMessage(null);
    try {
      const created = await adminApi.createQureEvalRun(
        file,
        selectedProjectId,
        Number(rowLimit),
      );
      setMessage(
        `QuRE Eval запущен: выбрано строк ${created.selected_rows} из ${created.total_rows}.`,
      );
      const runId = await loadRuns(created.id);
      await loadRun(runId);
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось запустить QuRE Eval."));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSelectRun(runId: string) {
    setSelectedRunId(runId);
    setError(null);
    try {
      await loadRun(runId);
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось загрузить QuRE Eval-запуск."));
    }
  }

  async function handleExport(format: "json" | "csv") {
    if (!activeRun) {
      return;
    }
    setError(null);
    try {
      const content = await adminApi.exportQureEvalRun(activeRun.id, format);
      downloadText(
        `qure-eval-${activeRun.id}.${format}`,
        content,
        format === "json" ? "application/json;charset=utf-8" : "text/csv;charset=utf-8",
      );
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось экспортировать QuRE Eval."));
    }
  }

  async function handleDeleteRun(runId: string) {
    setDeletingRunId(runId);
    setError(null);
    try {
      await adminApi.deleteQureEvalRun(runId);
      const nextRunId = await loadRuns(selectedRunId === runId ? "" : selectedRunId);
      await loadRun(nextRunId);
      setMessage("QuRE Eval-запуск удалён.");
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось удалить QuRE Eval-запуск."));
    } finally {
      setDeletingRunId(null);
    }
  }

  if (loading) {
    return <LoadingSpinner label="Загружаем QuRE Eval" />;
  }

  return (
    <section className="space-y-6">
      <div className="rounded-[20px] border border-[rgba(9,30,66,0.12)] bg-white p-6 shadow-sm">
        <p className="section-eyebrow">QuRE Dataset</p>
        <h2 className="mt-2 text-2xl font-semibold text-[#172b4d]">
          QuRE Eval
        </h2>
        <div className="mt-6 grid gap-4 lg:grid-cols-[1fr_1fr_160px_auto]">
          <label className="space-y-2 text-sm font-medium text-[#172b4d]">
            <span>Проект</span>
            <select
              className="w-full rounded-[10px] border border-[rgba(9,30,66,0.14)] px-3 py-2"
              value={selectedProjectId}
              onChange={(event) => setSelectedProjectId(event.target.value)}
            >
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
          </label>

          <label className="space-y-2 text-sm font-medium text-[#172b4d]">
            <span>Исходный QuRE.csv</span>
            <input
              accept=".csv,text/csv"
              className="block w-full text-sm text-[#44546f] file:mr-3 file:rounded-[8px] file:border-0 file:bg-[#e9f2ff] file:px-3 file:py-2 file:text-sm file:font-medium file:text-[#0c66e4]"
              type="file"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </label>

          <label className="space-y-2 text-sm font-medium text-[#172b4d]">
            <span>Лимит строк</span>
            <input
              className="w-full rounded-[10px] border border-[rgba(9,30,66,0.14)] px-3 py-2"
              min={1}
              step={1}
              type="number"
              value={rowLimit}
              onChange={(event) => setRowLimit(event.target.value)}
            />
          </label>

          <div className="flex items-end">
            <button
              className="rounded-[10px] bg-[#0c66e4] px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-[#0055cc] disabled:cursor-not-allowed disabled:bg-[#a5adba]"
              disabled={!canSubmit}
              type="button"
              onClick={() => void handleCreateRun()}
            >
              {submitting ? "Запускаем..." : "Запустить"}
            </button>
          </div>
        </div>
        {message ? <p className="mt-4 text-sm text-[#216e4e]">{message}</p> : null}
        {error ? <p className="mt-4 text-sm text-[#ae2a19]">{error}</p> : null}
      </div>

      <div className="grid gap-6 xl:grid-cols-[360px_1fr]">
        <aside className="rounded-[20px] border border-[rgba(9,30,66,0.12)] bg-white p-5 shadow-sm">
          <h3 className="text-lg font-semibold text-[#172b4d]">История запусков</h3>
          <div className="mt-4 space-y-3">
            {runs.length === 0 ? (
              <p className="text-sm text-[#626f86]">Запусков пока нет.</p>
            ) : (
              runs.map((run) => (
                <button
                  key={run.id}
                  className={[
                    "w-full rounded-[12px] border p-4 text-left transition",
                    selectedRunId === run.id
                      ? "border-[#85b8ff] bg-[#e9f2ff]"
                      : "border-[rgba(9,30,66,0.1)] bg-[#fafbfc] hover:bg-white",
                  ].join(" ")}
                  type="button"
                  onClick={() => void handleSelectRun(run.id)}
                >
                  <span className="block text-sm font-semibold text-[#172b4d]">
                    {run.filename}
                  </span>
                  <span className="mt-1 block text-xs text-[#626f86]">
                    {statusLabel(run.status)} · {run.selected_rows}/{run.total_rows}
                  </span>
                  <span className="mt-1 block text-xs text-[#626f86]">
                    {formatDateTimeFull(run.created_at)}
                  </span>
                </button>
              ))
            )}
          </div>
        </aside>

        <div className="space-y-6">
          {!activeRun ? (
            <div className="rounded-[20px] border border-[rgba(9,30,66,0.12)] bg-white p-6 text-sm text-[#626f86] shadow-sm">
              Выберите или запустите QuRE Eval.
            </div>
          ) : (
            <>
              <div className="rounded-[20px] border border-[rgba(9,30,66,0.12)] bg-white p-6 shadow-sm">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <p className="section-eyebrow">{statusLabel(activeRun.status)}</p>
                    <h3 className="mt-2 text-xl font-semibold text-[#172b4d]">
                      {activeRun.filename}
                    </h3>
                    <p className="mt-1 text-sm text-[#626f86]">
                      {activeRun.project_name ?? activeRun.project_id} · выбрано{" "}
                      {activeRun.selected_rows} из {activeRun.total_rows}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      className="rounded-[10px] border border-[rgba(9,30,66,0.14)] px-3 py-2 text-sm font-medium text-[#172b4d] hover:bg-[#f7f8f9]"
                      type="button"
                      onClick={() => void handleExport("json")}
                    >
                      JSON
                    </button>
                    <button
                      className="rounded-[10px] border border-[rgba(9,30,66,0.14)] px-3 py-2 text-sm font-medium text-[#172b4d] hover:bg-[#f7f8f9]"
                      type="button"
                      onClick={() => void handleExport("csv")}
                    >
                      CSV
                    </button>
                    <button
                      className="rounded-[10px] border border-[#ffd5d2] px-3 py-2 text-sm font-medium text-[#ae2a19] hover:bg-[#fff4f2] disabled:cursor-not-allowed disabled:opacity-60"
                      disabled={
                        deletingRunId === activeRun.id ||
                        ["queued", "running"].includes(activeRun.status)
                      }
                      type="button"
                      onClick={() => void handleDeleteRun(activeRun.id)}
                    >
                      Удалить
                    </button>
                  </div>
                </div>

                <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
                  {metricCards.map(([label, value]) => (
                    <div
                      key={String(label)}
                      className="rounded-[12px] border border-[rgba(9,30,66,0.1)] bg-[#fafbfc] p-4"
                    >
                      <p className="text-xs font-medium uppercase text-[#626f86]">
                        {label}
                      </p>
                      <p className="mt-2 text-2xl font-semibold text-[#172b4d]">
                        {metricValue(value)}
                      </p>
                    </div>
                  ))}
                </div>
              </div>

              <div className="overflow-hidden rounded-[20px] border border-[rgba(9,30,66,0.12)] bg-white shadow-sm">
                <div className="border-b border-[rgba(9,30,66,0.1)] px-6 py-4">
                  <h3 className="text-lg font-semibold text-[#172b4d]">
                    Результаты кейсов
                  </h3>
                </div>
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-[rgba(9,30,66,0.1)] text-sm">
                    <thead className="bg-[#f7f8f9] text-left text-xs uppercase text-[#626f86]">
                      <tr>
                        <th className="px-4 py-3">id</th>
                        <th className="px-4 py-3">weak_word</th>
                        <th className="px-4 py-3">QuRE</th>
                        <th className="px-4 py-3">validator</th>
                        <th className="px-4 py-3">judge</th>
                        <th className="px-4 py-3">status</th>
                        <th className="px-4 py-3">details</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[rgba(9,30,66,0.08)]">
                      {activeRun.case_results.map((item) => (
                        <tr key={item.id}>
                          <td className="px-4 py-3 font-medium text-[#172b4d]">
                            {item.source_id}
                          </td>
                          <td className="px-4 py-3 text-[#44546f]">
                            {item.weak_word}
                          </td>
                          <td className="px-4 py-3 text-[#44546f]">
                            {item.defect}
                          </td>
                          <td className="px-4 py-3 text-[#44546f]">
                            {actualVerdict(item)}
                          </td>
                          <td className="max-w-[280px] px-4 py-3 text-[#44546f]">
                            <span className="font-semibold text-[#172b4d]">
                              {metricValue(judgePassed(item))}
                            </span>
                            <span className="ml-2 text-xs text-[#626f86]">
                              score {metricValue(judgeScore(item))}
                            </span>
                            {judgeRationale(item) ? (
                              <p className="mt-1 text-xs text-[#626f86]">
                                {shortText(judgeRationale(item), 140)}
                              </p>
                            ) : null}
                          </td>
                          <td className="px-4 py-3 text-[#44546f]">
                            {statusLabel(item.status)}
                          </td>
                          <td className="px-4 py-3 text-[#44546f]">
                            <details className="min-w-[320px] rounded-[10px] border border-[rgba(9,30,66,0.1)] bg-[#fafbfc] p-3">
                              <summary className="cursor-pointer text-sm font-semibold text-[#0c66e4]">
                                Ответы
                              </summary>
                              <div className="mt-3 space-y-3">
                                <div>
                                  <h4 className="text-xs font-semibold uppercase text-[#626f86]">
                                    Ответ валидатора
                                  </h4>
                                  <pre className="mt-2 max-h-80 overflow-auto rounded-[8px] bg-white p-3 text-xs leading-5 text-[#172b4d]">
                                    {compactJson(item.actual_result)}
                                  </pre>
                                </div>
                                <div>
                                  <h4 className="text-xs font-semibold uppercase text-[#626f86]">
                                    Ответ judge
                                  </h4>
                                  <pre className="mt-2 max-h-80 overflow-auto rounded-[8px] bg-white p-3 text-xs leading-5 text-[#172b4d]">
                                    {compactJson(item.judge_payload)}
                                  </pre>
                                </div>
                              </div>
                            </details>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
