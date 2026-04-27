import { useEffect, useEffectEvent, useState } from "react";

import {
  adminApi,
  type QdrantCollectionDiagnosticRead,
  type QdrantMatchBand,
  type QdrantOverviewRead,
  type QdrantProjectCoverageRead,
  type QdrantScenario,
  type QdrantScenarioProbeRead,
  type QdrantTaskResyncRead,
} from "@/api/adminApi";
import { projectsApi, type ProjectRead } from "@/api/projectsApi";
import { tasksApi, type TaskRead } from "@/api/tasksApi";
import { LoadingSpinner } from "@/shared/components/LoadingSpinner";
import { getApiErrorMessage } from "@/shared/lib/apiError";
import { formatDateTimeFull, getTaskStatusLabel } from "@/shared/lib/locale";

type AdminTab = "overview" | "scenarios" | "coverage";
type ReviewState = "relevant" | "partial" | "irrelevant";

const ADMIN_TABS: Array<{ key: AdminTab; label: string }> = [
  { key: "overview", label: "Состояние" },
  { key: "scenarios", label: "Сценарии" },
  { key: "coverage", label: "Покрытие" },
];

const SCENARIO_OPTIONS: Array<{ key: QdrantScenario; label: string }> = [
  { key: "related_tasks", label: "Related tasks" },
  { key: "project_questions", label: "Project questions" },
  { key: "duplicate_proposal", label: "Duplicate proposal" },
];

function formatCount(value: number | null) {
  return value === null ? "н/д" : value.toLocaleString("ru-RU");
}

function formatScore(value: number | null) {
  return value === null ? "н/д" : value.toFixed(4);
}

function matchBandLabel(value: QdrantMatchBand | null) {
  switch (value) {
    case "above_threshold":
      return "Выше порога";
    case "near_threshold":
      return "Рядом с порогом";
    case "below_threshold":
      return "Ниже порога";
    default:
      return "Без порога";
  }
}

function collectionTone(collection: QdrantCollectionDiagnosticRead) {
  if (collection.error) {
    return "border-rose-200 bg-rose-50/80";
  }
  if (collection.warnings.length > 0) {
    return "border-amber-200 bg-amber-50/80";
  }
  return "border-emerald-200 bg-emerald-50/80";
}

function reviewLabel(state: ReviewState) {
  if (state === "relevant") {
    return "Релевантно";
  }
  if (state === "partial") {
    return "Частично";
  }
  return "Нерелевантно";
}

export default function QdrantAdminPage() {
  const [activeTab, setActiveTab] = useState<AdminTab>("overview");
  const [selectedScenario, setSelectedScenario] =
    useState<QdrantScenario>("related_tasks");
  const [overview, setOverview] = useState<QdrantOverviewRead | null>(null);
  const [overviewLoading, setOverviewLoading] = useState(true);
  const [overviewError, setOverviewError] = useState<string | null>(null);
  const [projects, setProjects] = useState<ProjectRead[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [tasks, setTasks] = useState<TaskRead[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string>("");
  const [projectLoading, setProjectLoading] = useState(false);
  const [projectError, setProjectError] = useState<string | null>(null);
  const [coverage, setCoverage] = useState<QdrantProjectCoverageRead | null>(
    null,
  );
  const [customQuery, setCustomQuery] = useState("");
  const [proposalText, setProposalText] = useState("");
  const [scenarioResult, setScenarioResult] =
    useState<QdrantScenarioProbeRead | null>(null);
  const [scenarioLoading, setScenarioLoading] = useState(false);
  const [scenarioError, setScenarioError] = useState<string | null>(null);
  const [manualReviews, setManualReviews] = useState<Record<string, ReviewState>>(
    {},
  );
  const [resyncingTaskId, setResyncingTaskId] = useState<string | null>(null);
  const [lastResync, setLastResync] = useState<QdrantTaskResyncRead | null>(
    null,
  );

  async function loadBootstrap() {
    try {
      setOverviewLoading(true);
      setOverviewError(null);
      const [overviewData, projectList] = await Promise.all([
        adminApi.getQdrantOverview(),
        projectsApi.list(),
      ]);
      setOverview(overviewData);
      setProjects(projectList);
      setSelectedProjectId((current) => current || projectList[0]?.id || "");
    } catch (caught) {
      setOverviewError(
        getApiErrorMessage(
          caught,
          "Не удалось загрузить обзор Qdrant и список проектов.",
        ),
      );
    } finally {
      setOverviewLoading(false);
    }
  }

  async function loadProjectData(projectId: string) {
    if (!projectId) {
      setTasks([]);
      setCoverage(null);
      return;
    }

    try {
      setProjectLoading(true);
      setProjectError(null);
      const [projectTasks, projectCoverage] = await Promise.all([
        tasksApi.list(projectId, { size: 100 }),
        adminApi.getQdrantProjectCoverage(projectId, 20),
      ]);
      setTasks(projectTasks);
      setCoverage(projectCoverage);
      setSelectedTaskId((current) => {
        if (current && projectTasks.some((task) => task.id === current)) {
          return current;
        }
        return projectTasks[0]?.id || "";
      });
    } catch (caught) {
      setProjectError(
        getApiErrorMessage(
          caught,
          "Не удалось загрузить покрытие проекта и список задач.",
        ),
      );
    } finally {
      setProjectLoading(false);
    }
  }

  const onLoadBootstrap = useEffectEvent(loadBootstrap);
  const onLoadProjectData = useEffectEvent(loadProjectData);

  useEffect(() => {
    void onLoadBootstrap();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!selectedProjectId) {
      return;
    }
    void onLoadProjectData(selectedProjectId);
  }, [selectedProjectId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleRunScenario(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId) {
      setScenarioError("Сначала выберите проект.");
      return;
    }

    try {
      setScenarioLoading(true);
      setScenarioError(null);
      setLastResync(null);

      const taskId = selectedTaskId || undefined;
      let nextResult: QdrantScenarioProbeRead;
      if (selectedScenario === "related_tasks") {
        nextResult = await adminApi.probeQdrantRelatedTasks({
          project_id: selectedProjectId,
          task_id: taskId,
          query_text: customQuery.trim() || undefined,
          exclude_task_id: taskId,
          limit: 5,
        });
      } else if (selectedScenario === "project_questions") {
        nextResult = await adminApi.probeQdrantProjectQuestions({
          project_id: selectedProjectId,
          task_id: taskId,
          query_text: customQuery.trim() || undefined,
          limit: 5,
        });
      } else {
        nextResult = await adminApi.probeQdrantDuplicateProposal({
          project_id: selectedProjectId,
          task_id: taskId,
          proposal_text: proposalText.trim(),
        });
      }

      setScenarioResult(nextResult);
      setManualReviews({});
    } catch (caught) {
      setScenarioError(
        getApiErrorMessage(
          caught,
          "Не удалось выполнить сценарий диагностики Qdrant.",
        ),
      );
    } finally {
      setScenarioLoading(false);
    }
  }

  async function handleResyncTask(taskId: string) {
    try {
      setResyncingTaskId(taskId);
      setProjectError(null);
      const result = await adminApi.resyncQdrantTask(taskId);
      setLastResync(result);
      if (selectedProjectId) {
        await loadProjectData(selectedProjectId);
      }
    } catch (caught) {
      setProjectError(
        getApiErrorMessage(
          caught,
          "Не удалось пересинхронизировать индекс задачи.",
        ),
      );
    } finally {
      setResyncingTaskId(null);
    }
  }

  function renderOverview() {
    if (overviewLoading && !overview) {
      return <LoadingSpinner label="Загрузка диагностики Qdrant" />;
    }

    return (
      <div className="space-y-6">
        <div className="grid gap-4 md:grid-cols-3">
          <article className="glass-panel rounded-[24px] border border-black/10 p-5 shadow-panel">
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-ink/45">
              Соединение
            </p>
            <p className="mt-3 text-2xl font-extrabold text-ink">
              {overview?.connected ? "Подключено" : "Нет соединения"}
            </p>
            <p className="mt-2 text-sm text-ink/60">
              {overview?.qdrant_url ?? "Qdrant URL не определён"}
            </p>
          </article>
          <article className="glass-panel rounded-[24px] border border-black/10 p-5 shadow-panel">
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-ink/45">
              Эмбеддинги
            </p>
            <p className="mt-3 text-2xl font-extrabold text-ink">
              {overview?.embedding_provider ?? "не задан"}
            </p>
            <p className="mt-2 text-sm text-ink/60">
              {overview?.embedding_model ?? "Модель не указана"}
            </p>
          </article>
          <article className="glass-panel rounded-[24px] border border-black/10 p-5 shadow-panel">
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-ink/45">
              Ожидаемый vector size
            </p>
            <p className="mt-3 text-2xl font-extrabold text-ink">
              {formatCount(overview?.expected_vector_size ?? null)}
            </p>
            <p className="mt-2 text-sm text-ink/60">
              Обновлено:{" "}
              {overview ? formatDateTimeFull(overview.generated_at) : "н/д"}
            </p>
          </article>
        </div>

        {overviewError ? (
          <p className="rounded-2xl bg-rose-100 px-4 py-3 text-sm text-rose-700">
            {overviewError}
          </p>
        ) : null}

        {overview?.connection_error ? (
          <p className="rounded-2xl bg-amber-100 px-4 py-3 text-sm text-amber-800">
            {overview.connection_error}
          </p>
        ) : null}

        <div className="grid gap-4 xl:grid-cols-3">
          {(overview?.collections ?? []).map((collection) => (
            <article
              key={collection.collection_name}
              className={`rounded-[26px] border p-5 shadow-panel ${collectionTone(collection)}`}
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-xs font-bold uppercase tracking-[0.16em] text-ink/45">
                    Коллекция
                  </p>
                  <h4 className="mt-2 text-xl font-bold text-ink">
                    {collection.collection_name}
                  </h4>
                </div>
                <span className="rounded-full bg-white/80 px-3 py-1 text-xs font-semibold text-ink/65">
                  {collection.exists ? "live" : "missing"}
                </span>
              </div>

              <dl className="mt-5 grid gap-3 text-sm text-ink/75">
                <div className="flex items-center justify-between gap-3">
                  <dt>Точек</dt>
                  <dd className="font-semibold text-ink">
                    {formatCount(collection.points_count)}
                  </dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt>Индексированных векторов</dt>
                  <dd className="font-semibold text-ink">
                    {formatCount(collection.indexed_vectors_count)}
                  </dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt>Размер вектора</dt>
                  <dd className="font-semibold text-ink">
                    {formatCount(collection.vector_size)}
                  </dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt>Distance</dt>
                  <dd className="font-semibold text-ink">
                    {collection.distance ?? "н/д"}
                  </dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt>Payload keys</dt>
                  <dd className="font-semibold text-ink">
                    {collection.sample_payload_keys.length > 0
                      ? collection.sample_payload_keys.join(", ")
                      : "нет sample"}
                  </dd>
                </div>
              </dl>

              <div className="mt-5 flex flex-wrap gap-2 text-xs">
                <span className="rounded-full bg-white/75 px-3 py-1 text-ink/70">
                  provider:{" "}
                  {collection.provider_matches === true
                    ? "ok"
                    : collection.provider_matches === false
                      ? "mismatch"
                      : "n/a"}
                </span>
                <span className="rounded-full bg-white/75 px-3 py-1 text-ink/70">
                  model:{" "}
                  {collection.model_matches === true
                    ? "ok"
                    : collection.model_matches === false
                      ? "mismatch"
                      : "n/a"}
                </span>
                <span className="rounded-full bg-white/75 px-3 py-1 text-ink/70">
                  vector:{" "}
                  {collection.vector_size_matches === true
                    ? "ok"
                    : collection.vector_size_matches === false
                      ? "mismatch"
                      : "n/a"}
                </span>
              </div>

              {collection.warnings.length > 0 ? (
                <div className="mt-5 space-y-2 rounded-[20px] bg-white/75 p-4 text-sm text-amber-900">
                  {collection.warnings.map((warning) => (
                    <p key={warning}>{warning}</p>
                  ))}
                </div>
              ) : null}

              {collection.error ? (
                <p className="mt-5 rounded-[20px] bg-rose-100 px-4 py-3 text-sm text-rose-700">
                  {collection.error}
                </p>
              ) : null}
            </article>
          ))}
        </div>
      </div>
    );
  }

  function renderScenarios() {
    return (
      <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <form
          className="glass-panel space-y-5 rounded-[28px] border border-black/10 p-6 shadow-panel"
          onSubmit={handleRunScenario}
        >
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-ember">
              Live-проверка
            </p>
            <h3 className="mt-2 text-2xl font-extrabold text-ink">
              Сценарии поиска и дедупликации
            </h3>
            <p className="mt-3 text-sm leading-7 text-ink/70">
              Выберите проект, задачу и сценарий. Запрос можно оставить пустым,
              тогда backend возьмёт контекст задачи автоматически.
            </p>
          </div>

          {projectError ? (
            <p className="rounded-2xl bg-rose-100 px-4 py-3 text-sm text-rose-700">
              {projectError}
            </p>
          ) : null}

          {scenarioError ? (
            <p className="rounded-2xl bg-rose-100 px-4 py-3 text-sm text-rose-700">
              {scenarioError}
            </p>
          ) : null}

          <label className="block">
            <span className="mb-2 block text-sm font-semibold text-ink/70">
              Проект
            </span>
            <select
              className="ui-field"
              onChange={(event) => setSelectedProjectId(event.target.value)}
              value={selectedProjectId}
            >
              <option value="">Выберите проект</option>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="mb-2 block text-sm font-semibold text-ink/70">
              Задача
            </span>
            <select
              className="ui-field"
              onChange={(event) => setSelectedTaskId(event.target.value)}
              value={selectedTaskId}
            >
              <option value="">Без привязки к задаче</option>
              {tasks.map((task) => (
                <option key={task.id} value={task.id}>
                  {task.title}
                </option>
              ))}
            </select>
          </label>

          <div className="flex flex-wrap gap-2">
            {SCENARIO_OPTIONS.map((option) => (
              <button
                key={option.key}
                className={
                  selectedScenario === option.key
                    ? "ui-button-primary"
                    : "ui-button-secondary"
                }
                onClick={() => setSelectedScenario(option.key)}
                type="button"
              >
                {option.label}
              </button>
            ))}
          </div>

          {selectedScenario === "duplicate_proposal" ? (
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-ink/70">
                Текст предложения
              </span>
              <textarea
                className="ui-field min-h-[180px]"
                onChange={(event) => setProposalText(event.target.value)}
                value={proposalText}
              />
            </label>
          ) : (
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-ink/70">
                Переопределить query
              </span>
              <textarea
                className="ui-field min-h-[180px]"
                onChange={(event) => setCustomQuery(event.target.value)}
                placeholder="Можно оставить пустым и использовать title/content выбранной задачи."
                value={customQuery}
              />
            </label>
          )}

          <button
            className={scenarioLoading ? "ui-button-secondary" : "ui-button-primary"}
            disabled={scenarioLoading || !selectedProjectId}
            type="submit"
          >
            {scenarioLoading ? "Запускаем live-проверку..." : "Запустить сценарий"}
          </button>
        </form>

        <section className="glass-panel rounded-[28px] border border-black/10 p-6 shadow-panel">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-ember">
              Результат
            </p>
            <h3 className="mt-2 text-2xl font-extrabold text-ink">
              Выдача и эвристики
            </h3>
          </div>

          {!scenarioResult ? (
            <div className="mt-5 rounded-[24px] border border-dashed border-black/10 bg-white/60 px-5 py-8 text-sm leading-7 text-ink/55">
              После запуска сценария здесь появятся top-k результаты, предупреждения
              и локальная ручная оценка релевантности.
            </div>
          ) : (
            <div className="mt-5 space-y-4">
              <article className="rounded-[22px] border border-black/10 bg-white/70 p-4">
                <p className="text-xs font-bold uppercase tracking-[0.14em] text-ink/45">
                  Query
                </p>
                <pre className="mt-3 whitespace-pre-wrap break-words font-mono text-sm leading-7 text-ink">
                  {scenarioResult.query_text || "Пустой query"}
                </pre>
                {scenarioResult.raw_threshold !== null ? (
                  <p className="mt-3 text-sm text-ink/70">
                    Рабочий threshold: {scenarioResult.raw_threshold.toFixed(2)}
                  </p>
                ) : null}
              </article>

              {scenarioResult.heuristics.length > 0 ? (
                <div className="space-y-3">
                  {scenarioResult.heuristics.map((heuristic) => (
                    <article
                      key={heuristic.code}
                      className="rounded-[22px] border border-amber-200 bg-amber-50 p-4"
                    >
                      <p className="text-sm font-semibold text-amber-900">
                        {heuristic.message}
                      </p>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="rounded-[22px] border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
                  Явных эвристических проблем не обнаружено.
                </p>
              )}

              {(scenarioResult.results ?? []).length === 0 ? (
                <p className="rounded-[22px] border border-dashed border-black/10 bg-white/60 px-4 py-6 text-sm text-ink/55">
                  Сценарий отработал, но Qdrant не вернул результатов.
                </p>
              ) : (
                scenarioResult.results.map((result) => (
                  <article
                    key={result.id}
                    className="rounded-[24px] border border-black/10 bg-white/80 p-5"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-lg font-bold text-ink">
                          {result.task_title ?? result.id}
                        </p>
                        <p className="mt-1 text-sm text-ink/65">
                          {result.task_status
                            ? getTaskStatusLabel(result.task_status)
                            : "Статус не указан"}
                          {" · "}score: {formatScore(result.score)}
                          {result.match_band ? (
                            <>
                              {" · "}
                              {matchBandLabel(result.match_band)}
                            </>
                          ) : null}
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {(["relevant", "partial", "irrelevant"] as ReviewState[]).map(
                          (state) => (
                            <button
                              key={state}
                              className={
                                manualReviews[result.id] === state
                                  ? "ui-button-primary"
                                  : "ui-button-secondary"
                              }
                              onClick={() =>
                                setManualReviews((current) => ({
                                  ...current,
                                  [result.id]: state,
                                }))
                              }
                              type="button"
                            >
                              {reviewLabel(state)}
                            </button>
                          ),
                        )}
                      </div>
                    </div>

                    <pre className="mt-4 whitespace-pre-wrap break-words rounded-[20px] bg-[#f8fafc] p-4 font-mono text-sm leading-7 text-ink">
                      {result.snippet}
                    </pre>

                    {result.metadata ? (
                      <details className="mt-4 rounded-[20px] border border-black/10 bg-white/70 p-4">
                        <summary className="cursor-pointer text-sm font-semibold text-ink">
                          Метаданные результата
                        </summary>
                        <pre className="mt-3 whitespace-pre-wrap break-words font-mono text-xs leading-6 text-ink/75">
                          {JSON.stringify(result.metadata, null, 2)}
                        </pre>
                      </details>
                    ) : null}
                  </article>
                ))
              )}
            </div>
          )}
        </section>
      </div>
    );
  }

  function renderCoverage() {
    if (projectLoading && !coverage) {
      return <LoadingSpinner label="Загрузка покрытия проекта" />;
    }

    return (
      <div className="space-y-6">
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          <article className="glass-panel rounded-[24px] border border-black/10 p-5 shadow-panel">
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-ink/45">
              Всего задач
            </p>
            <p className="mt-3 text-2xl font-extrabold text-ink">
              {coverage?.summary.tasks_total ?? 0}
            </p>
          </article>
          <article className="glass-panel rounded-[24px] border border-black/10 p-5 shadow-panel">
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-ink/45">
              Индексированы
            </p>
            <p className="mt-3 text-2xl font-extrabold text-ink">
              {coverage?.summary.indexed_tasks_total ?? 0}
            </p>
          </article>
          <article className="glass-panel rounded-[24px] border border-black/10 p-5 shadow-panel">
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-ink/45">
              Stale
            </p>
            <p className="mt-3 text-2xl font-extrabold text-ink">
              {coverage?.summary.stale_tasks_total ?? 0}
            </p>
          </article>
          <article className="glass-panel rounded-[24px] border border-black/10 p-5 shadow-panel">
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-ink/45">
              С knowledge points
            </p>
            <p className="mt-3 text-2xl font-extrabold text-ink">
              {coverage?.summary.tasks_with_knowledge_total ?? 0}
            </p>
          </article>
          <article className="glass-panel rounded-[24px] border border-black/10 p-5 shadow-panel">
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-ink/45">
              С project questions
            </p>
            <p className="mt-3 text-2xl font-extrabold text-ink">
              {coverage?.summary.tasks_with_questions_total ?? 0}
            </p>
          </article>
        </div>

        {projectError ? (
          <p className="rounded-2xl bg-rose-100 px-4 py-3 text-sm text-rose-700">
            {projectError}
          </p>
        ) : null}

        {lastResync ? (
          <article className="rounded-[24px] border border-emerald-200 bg-emerald-50 p-5">
            <p className="text-sm font-semibold text-emerald-900">
              Индекс задачи пересобран
            </p>
            <p className="mt-2 text-sm text-emerald-900/85">
              Chunk ids: {lastResync.chunk_ids.length}. Knowledge points:{" "}
              {lastResync.knowledge_points_count}. Project questions:{" "}
              {lastResync.question_points_count}.
            </p>
            {lastResync.warnings.length > 0 ? (
              <div className="mt-3 space-y-2 text-sm text-emerald-900/85">
                {lastResync.warnings.map((warning) => (
                  <p key={warning}>{warning}</p>
                ))}
              </div>
            ) : null}
          </article>
        ) : null}

        <div className="space-y-4">
          {(coverage?.items ?? []).map((item) => (
            <article
              key={item.id}
              className="glass-panel rounded-[26px] border border-black/10 p-5 shadow-panel"
            >
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <p className="text-lg font-bold text-ink">{item.title}</p>
                  <p className="mt-1 text-sm text-ink/65">
                    {getTaskStatusLabel(item.status)}
                    {" · "}knowledge: {item.knowledge_points_count}
                    {" · "}questions: {item.question_points_count}
                    {" · "}manual questions: {item.validation_questions_total}
                  </p>
                  <p className="mt-2 text-sm text-ink/60">
                    Indexed at:{" "}
                    {item.indexed_at ? formatDateTimeFull(item.indexed_at) : "не индексировалась"}
                    {" · "}Updated at: {formatDateTimeFull(item.updated_at)}
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2 text-xs">
                    <span className="rounded-full bg-[#e9f2ff] px-3 py-1 text-[#0c66e4]">
                      {item.embeddings_stale ? "embeddings stale" : "embeddings synced"}
                    </span>
                    {item.requires_revalidation ? (
                      <span className="rounded-full bg-amber-100 px-3 py-1 text-amber-800">
                        requires revalidation
                      </span>
                    ) : null}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    className="ui-button-secondary"
                    onClick={() => {
                      setSelectedProjectId(coverage?.project_id ?? "");
                      setSelectedTaskId(item.id);
                      setSelectedScenario("related_tasks");
                      setActiveTab("scenarios");
                    }}
                    type="button"
                  >
                    Проверить сценарий
                  </button>
                  <button
                    className={
                      resyncingTaskId === item.id
                        ? "ui-button-secondary"
                        : "ui-button-primary"
                    }
                    disabled={resyncingTaskId === item.id}
                    onClick={() => void handleResyncTask(item.id)}
                    type="button"
                  >
                    {resyncingTaskId === item.id
                      ? "Пересинхронизируем..."
                      : "Пересинхронизировать индекс"}
                  </button>
                </div>
              </div>
            </article>
          ))}
        </div>
      </div>
    );
  }

  return (
    <section className="space-y-6">
      <header className="glass-panel rounded-[28px] border border-black/10 p-6 shadow-panel">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-ember">
              Qdrant Diagnostics
            </p>
            <h3 className="mt-2 text-2xl font-extrabold text-ink sm:text-3xl">
              Проверка качества Qdrant и RAG-сценариев
            </h3>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-ink/70">
              Страница собирает живую статистику коллекций, даёт ручной прогон
              основных сценариев поиска и показывает фактическое покрытие задач
              индексами Qdrant.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {ADMIN_TABS.map((tab) => (
              <button
                key={tab.key}
                className={activeTab === tab.key ? "ui-button-primary" : "ui-button-secondary"}
                onClick={() => setActiveTab(tab.key)}
                type="button"
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </header>

      {activeTab === "overview" ? renderOverview() : null}
      {activeTab === "scenarios" ? renderScenarios() : null}
      {activeTab === "coverage" ? renderCoverage() : null}
    </section>
  );
}
