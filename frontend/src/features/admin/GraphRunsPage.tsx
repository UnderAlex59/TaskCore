import {
  useEffect,
  useEffectEvent,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  adminApi,
  type GraphRunDetailRead,
  type GraphRunGraphViewRead,
  type GraphRunNodeRead,
  type GraphRunPageRead,
  type GraphRunStatus,
  type LLMRequestLogPageRead,
  type LLMRuntimeSettingsRead,
  type MonitoringRange,
} from "@/api/adminApi";
import { LoadingSpinner } from "@/shared/components/LoadingSpinner";
import { getApiErrorMessage } from "@/shared/lib/apiError";
import {
  formatCurrencyUsd,
  formatDateTimeWithSeconds,
  getAgentKeyLabel,
  getMonitoringRangeLabel,
  getProviderKindLabel,
} from "@/shared/lib/locale";

const RANGE_OPTIONS: MonitoringRange[] = ["24h", "7d", "30d", "90d"];
let mermaidInitialized = false;

type StatusFilter = "all" | GraphRunStatus;
type DetailTab = "timeline" | "graph";
type LLMRequestItem = LLMRequestLogPageRead["items"][number];

const STATUS_OPTIONS: Array<{ label: string; value: StatusFilter }> = [
  { value: "all", label: "Все" },
  { value: "success", label: "Успешные" },
  { value: "error", label: "Ошибки" },
  { value: "running", label: "В работе" },
];

const GRAPH_LABELS: Record<string, string> = {
  attachment_vision_graph: "Vision вложений",
  change_tracker_agent_graph: "Change tracker",
  chat_graph: "Чат",
  chat_routing_eval_graph: "Orchestrator Eval",
  manager_agent_graph: "Manager",
  provider_test_graph: "Проверка провайдера",
  qa_agent_graph: "QA",
  rag_pipeline: "RAG индексация",
  rag_retrieval_graph: "RAG retrieval",
  task_tag_suggestion_graph: "Подбор тегов",
  validation_graph: "Валидация задачи",
  vision_test_graph: "Vision тест",
};

function getGraphLabel(graphKey: string | null | undefined) {
  if (!graphKey) {
    return "Граф не указан";
  }
  return GRAPH_LABELS[graphKey] ?? graphKey.replaceAll("_", " ");
}

function getStatusLabel(status: GraphRunStatus) {
  if (status === "success") return "Успешно";
  if (status === "error") return "Ошибка";
  return "В работе";
}

function formatLatency(value: number | null) {
  return value === null ? "н/д" : `${value} мс`;
}

function formatJson(value: unknown) {
  return value === null || value === undefined
    ? "Нет данных"
    : JSON.stringify(value, null, 2);
}

function flattenNodes(nodes: GraphRunNodeRead[]) {
  const result: GraphRunNodeRead[] = [];
  function visit(items: GraphRunNodeRead[]) {
    for (const item of items) {
      result.push(item);
      visit(item.children);
    }
  }
  visit(nodes);
  return result;
}

function getNodeLlmRequests(
  node: GraphRunNodeRead | null,
  requests: LLMRequestItem[],
) {
  if (!node) {
    return [];
  }
  if (node.llm_request_ids.length > 0) {
    const ids = new Set(node.llm_request_ids);
    return requests.filter((item) => ids.has(item.id));
  }
  return requests.filter((item) => item.graph_node_name === node.node_name);
}

export default function GraphRunsPage() {
  const [range, setRange] = useState<MonitoringRange>("7d");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [page, setPage] = useState(1);
  const [runs, setRuns] = useState<GraphRunPageRead | null>(null);
  const [settings, setSettings] = useState<LLMRuntimeSettingsRead | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [detail, setDetail] = useState<GraphRunDetailRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [savingMonitoring, setSavingMonitoring] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadData(
    activeRange: MonitoringRange,
    activeStatus: StatusFilter,
    activePage: number,
  ) {
    try {
      setLoading(true);
      setError(null);
      const [loadedRuns, loadedSettings] = await Promise.all([
        adminApi.getGraphRuns({
          page: activePage,
          range: activeRange,
          status: activeStatus === "all" ? undefined : activeStatus,
        }),
        adminApi.getLlmRuntimeSettings(),
      ]);
      setRuns(loadedRuns);
      setSettings(loadedSettings);
    } catch (caught) {
      setError(
        getApiErrorMessage(
          caught,
          "Не удалось загрузить запуски графов.",
        ),
      );
    } finally {
      setLoading(false);
    }
  }

  const onLoadData = useEffectEvent(loadData);

  useEffect(() => {
    void onLoadData(range, statusFilter, page);
  }, [range, statusFilter, page]); // eslint-disable-line react-hooks/exhaustive-deps

  async function openDetail(runId: string) {
    setSelectedRunId(runId);
    try {
      setDetailLoading(true);
      setError(null);
      setDetail(await adminApi.getGraphRunDetail(runId));
    } catch (caught) {
      setError(
        getApiErrorMessage(
          caught,
          "Не удалось загрузить детали запуска графа.",
        ),
      );
    } finally {
      setDetailLoading(false);
    }
  }

  async function toggleGraphMonitoring() {
    if (!settings) {
      return;
    }
    const nextValue = !settings.graph_monitoring_enabled;
    try {
      setSavingMonitoring(true);
      setError(null);
      setSettings(
        await adminApi.updateLlmRuntimeSettings({
          graph_monitoring_enabled: nextValue,
        }),
      );
    } catch (caught) {
      setError(
        getApiErrorMessage(
          caught,
          "Не удалось обновить режим мониторинга графов.",
        ),
      );
    } finally {
      setSavingMonitoring(false);
    }
  }

  function changeRange(nextRange: MonitoringRange) {
    setPage(1);
    setRange(nextRange);
  }

  function changeStatus(nextStatus: StatusFilter) {
    setPage(1);
    setStatusFilter(nextStatus);
  }

  if (loading && !runs) {
    return <LoadingSpinner label="Загрузка запусков графов" />;
  }

  const totalPages = runs
    ? Math.max(1, Math.ceil(runs.total / runs.page_size))
    : 1;
  const graphMonitoringEnabled = settings?.graph_monitoring_enabled ?? true;

  return (
    <section className="space-y-5">
      <header className="rounded-[16px] border border-black/10 bg-white p-5">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.14em] text-ink/55">
              LangGraph
            </p>
            <h3 className="mt-2 text-2xl font-semibold text-ink">
              Запуски графов
            </h3>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-ink/65">
              История выполнения графов: фактические узлы, входные и выходные
              данные, вложенные subgraph и выбранные переходы.
            </p>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <button
              className={
                graphMonitoringEnabled ? "ui-button-primary" : "ui-button-secondary"
              }
              disabled={savingMonitoring}
              onClick={() => void toggleGraphMonitoring()}
              type="button"
            >
              {graphMonitoringEnabled
                ? "Мониторинг включен"
                : "Мониторинг выключен"}
            </button>
            <button
              className="ui-button-secondary"
              disabled={loading}
              onClick={() => void loadData(range, statusFilter, page)}
              type="button"
            >
              Обновить
            </button>
          </div>
        </div>
        {!graphMonitoringEnabled ? (
          <p className="mt-4 rounded-[10px] bg-[#f2b705]/15 px-4 py-3 text-sm text-[#6f5300]">
            Новые запуски графов не будут записываться, пока мониторинг
            выключен.
          </p>
        ) : null}
        {error ? (
          <p className="mt-4 rounded-[10px] bg-ember/10 px-4 py-3 text-sm text-ember">
            {error}
          </p>
        ) : null}
      </header>

      <section className="rounded-[16px] border border-black/10 bg-white p-5">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <div className="flex flex-wrap gap-2">
            {RANGE_OPTIONS.map((item) => (
              <button
                key={item}
                className={
                  item === range ? "ui-button-primary" : "ui-button-secondary"
                }
                onClick={() => changeRange(item)}
                type="button"
              >
                {getMonitoringRangeLabel(item)}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            {STATUS_OPTIONS.map((item) => (
              <button
                key={item.value}
                className={
                  item.value === statusFilter
                    ? "ui-button-primary"
                    : "ui-button-secondary"
                }
                onClick={() => changeStatus(item.value)}
                type="button"
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-5 overflow-x-auto">
          <table className="min-w-full divide-y divide-black/10 text-left text-sm">
            <thead className="text-xs uppercase tracking-[0.12em] text-ink/45">
              <tr>
                <th className="px-3 py-3 font-semibold">Граф</th>
                <th className="px-3 py-3 font-semibold">Статус</th>
                <th className="px-3 py-3 font-semibold">Время</th>
                <th className="px-3 py-3 font-semibold">Длительность</th>
                <th className="px-3 py-3 font-semibold">Контекст</th>
                <th className="px-3 py-3 font-semibold">Узлы / LLM</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-black/10">
              {(runs?.items ?? []).map((item) => (
                <tr
                  key={item.id}
                  className={
                    selectedRunId === item.id
                      ? "bg-[#f3f7fb]"
                      : "hover:bg-[#f7f8fa]"
                  }
                >
                  <td className="px-3 py-3">
                    <button
                      className="text-left font-semibold text-[#0c66e4] hover:underline"
                      onClick={() => void openDetail(item.id)}
                      type="button"
                    >
                      {getGraphLabel(item.graph_key)}
                    </button>
                    <p className="mt-1 text-xs text-ink/45">
                      {item.source ?? "source не указан"}
                    </p>
                  </td>
                  <td className="px-3 py-3">
                    <StatusPill status={item.status} />
                  </td>
                  <td className="px-3 py-3 text-ink/70">
                    {formatDateTimeWithSeconds(item.started_at)}
                  </td>
                  <td className="px-3 py-3 text-ink/70">
                    {formatLatency(item.latency_ms)}
                  </td>
                  <td className="px-3 py-3 text-xs leading-5 text-ink/60">
                    <div>Проект: {item.project_id ?? "н/д"}</div>
                    <div>Задача: {item.task_id ?? "н/д"}</div>
                    <div>{item.actor_name}</div>
                  </td>
                  <td className="px-3 py-3 text-ink/70">
                    {item.events_count} / {item.llm_requests_count}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {(runs?.items ?? []).length === 0 ? (
            <p className="rounded-[12px] border border-dashed border-black/10 px-4 py-6 text-sm text-ink/55">
              В выбранном окне запусков графов нет.
            </p>
          ) : null}
        </div>

        <div className="mt-5 flex items-center justify-between text-sm text-ink/60">
          <span>
            Всего: {runs?.total ?? 0}. Страница {page} из {totalPages}.
          </span>
          <div className="flex gap-2">
            <button
              className="ui-button-secondary"
              disabled={page <= 1}
              onClick={() => setPage(page - 1)}
              type="button"
            >
              Назад
            </button>
            <button
              className="ui-button-secondary"
              disabled={page >= totalPages}
              onClick={() => setPage(page + 1)}
              type="button"
            >
              Вперед
            </button>
          </div>
        </div>
      </section>

      <GraphRunDetailPanel detail={detail} loading={detailLoading} />
    </section>
  );
}

function StatusPill({ status }: { status: GraphRunStatus }) {
  return (
    <span
      className={
        status === "success"
          ? "rounded-full bg-pine/15 px-2.5 py-1 text-xs font-bold text-pine"
          : status === "error"
            ? "rounded-full bg-ember/12 px-2.5 py-1 text-xs font-bold text-ember"
            : "rounded-full bg-[#f2b705]/15 px-2.5 py-1 text-xs font-bold text-[#7a5a00]"
      }
    >
      {getStatusLabel(status)}
    </span>
  );
}

function GraphRunDetailPanel({
  detail,
  loading,
}: {
  detail: GraphRunDetailRead | null;
  loading: boolean;
}) {
  const [activeTab, setActiveTab] = useState<DetailTab>("timeline");

  useEffect(() => {
    setActiveTab("timeline");
  }, [detail?.id]);

  if (loading) {
    return <LoadingSpinner label="Загрузка деталей графа" />;
  }
  if (!detail) {
    return null;
  }

  return (
    <section className="rounded-[16px] border border-black/10 bg-white p-5">
      <div className="flex flex-col gap-2 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.14em] text-ink/45">
            Детали запуска
          </p>
          <h3 className="mt-2 text-xl font-semibold text-ink">
            {getGraphLabel(detail.graph_key)}
          </h3>
          <p className="mt-1 text-sm text-ink/60">
            {detail.id} / {getStatusLabel(detail.status)} /{" "}
            {formatLatency(detail.latency_ms)}
          </p>
        </div>
        {detail.error_message ? (
          <p className="max-w-xl rounded-[10px] bg-ember/10 px-3 py-2 text-sm text-ember">
            {detail.error_message}
          </p>
        ) : null}
      </div>

      <div className="mt-5 flex flex-wrap gap-2" role="tablist">
        <button
          className={
            activeTab === "timeline" ? "ui-button-primary" : "ui-button-secondary"
          }
          onClick={() => setActiveTab("timeline")}
          role="tab"
          type="button"
        >
          Timeline
        </button>
        <button
          className={
            activeTab === "graph" ? "ui-button-primary" : "ui-button-secondary"
          }
          onClick={() => setActiveTab("graph")}
          role="tab"
          type="button"
        >
          Граф
        </button>
      </div>

      {activeTab === "timeline" ? (
        <TimelineTab detail={detail} />
      ) : (
        <GraphTab detail={detail} />
      )}
    </section>
  );
}

function TimelineTab({ detail }: { detail: GraphRunDetailRead }) {
  return (
    <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
      <div>
        <h4 className="text-sm font-bold text-ink">Выполнение узлов</h4>
        <div className="mt-3 space-y-2">
          {detail.node_tree.length === 0 ? (
            <p className="text-sm text-ink/55">
              Для запуска нет записанных узлов.
            </p>
          ) : (
            detail.node_tree.map((node) => (
              <NodeTreeItem key={node.id} node={node} />
            ))
          )}
        </div>

        {detail.transitions.length > 0 ? (
          <>
            <h4 className="mt-6 text-sm font-bold text-ink">
              Условия переходов
            </h4>
            <TransitionList detail={detail} />
          </>
        ) : null}

        <h4 className="mt-6 text-sm font-bold text-ink">
          Связанные LLM-вызовы
        </h4>
        <LLMRequestList items={detail.llm_requests} />
      </div>

      <div className="space-y-4">
        <Preview title="Input preview" value={detail.input_preview} />
        <Preview title="Final state preview" value={detail.final_state_preview} />
      </div>
    </div>
  );
}

function NodeTreeItem({ node }: { node: GraphRunNodeRead }) {
  const [open, setOpen] = useState(false);
  const hasChildren = node.children.length > 0;
  return (
    <article className="rounded-[12px] border border-black/10 p-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-semibold text-ink">#{node.sequence}</span>
            <span className="font-semibold text-ink">{node.node_name}</span>
            <StatusPill status={node.status} />
          </div>
          <p className="mt-1 text-xs text-ink/45">
            {getGraphLabel(node.graph_key)} /{" "}
            {node.namespace ?? "namespace не указан"} /{" "}
            {formatLatency(node.latency_ms)}
          </p>
        </div>
        <button
          className="ui-button-secondary"
          onClick={() => setOpen((current) => !current)}
          type="button"
        >
          {open ? "Свернуть" : "Данные"}
        </button>
      </div>

      {node.error_message ? (
        <p className="mt-3 rounded-[10px] bg-ember/10 px-3 py-2 text-sm text-ember">
          {node.error_message}
        </p>
      ) : null}

      {open ? (
        <div className="grid gap-3 xl:grid-cols-2">
          <Preview title="Вход узла" value={node.input_preview} />
          <Preview title="Выход узла" value={node.result_preview} />
        </div>
      ) : null}

      {hasChildren ? (
        <div className="mt-3 border-l-2 border-[#d8dee8] pl-3">
          <p className="mb-2 text-xs font-bold uppercase tracking-[0.12em] text-ink/45">
            Вложенный граф
          </p>
          <div className="space-y-2">
            {node.children.map((child) => (
              <NodeTreeItem key={child.id} node={child} />
            ))}
          </div>
        </div>
      ) : null}
    </article>
  );
}

function GraphTab({ detail }: { detail: GraphRunDetailRead }) {
  const nodeByEventId = useMemo(() => {
    const map = new Map<string, GraphRunNodeRead>();
    for (const node of flattenNodes(detail.node_tree)) {
      map.set(node.id, node);
    }
    return map;
  }, [detail.node_tree]);

  if (detail.graph_views.length === 0) {
    return (
      <p className="mt-5 rounded-[12px] border border-dashed border-black/10 px-4 py-6 text-sm text-ink/55">
        Для этого запуска нет Mermaid-схемы.
      </p>
    );
  }
  return (
    <div className="mt-5 space-y-4">
      {detail.graph_views.map((view) => (
        <MermaidGraph
          detail={detail}
          key={view.graph_key}
          nodeByEventId={nodeByEventId}
          view={view}
        />
      ))}
    </div>
  );
}

function MermaidGraph({
  detail,
  nodeByEventId,
  view,
}: {
  detail: GraphRunDetailRead;
  nodeByEventId: Map<string, GraphRunNodeRead>;
  view: GraphRunGraphViewRead;
}) {
  const reactId = useId().replaceAll(":", "");
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [svg, setSvg] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [selectedMermaidNodeId, setSelectedMermaidNodeId] = useState<string | null>(
    null,
  );

  const selectedGraphNode = view.nodes.find(
    (node) => node.mermaid_id === selectedMermaidNodeId,
  );
  const selectedRunNode = selectedGraphNode?.node_event_id
    ? nodeByEventId.get(selectedGraphNode.node_event_id) ?? null
    : null;
  const nodeLlmRequests = getNodeLlmRequests(selectedRunNode, detail.llm_requests);
  const transitions = detail.transitions.filter(
    (item) => item.graph_key === view.graph_key,
  );

  useEffect(() => {
    let cancelled = false;
    async function renderGraph() {
      try {
        const { default: mermaid } = await import("mermaid");
        if (!mermaidInitialized) {
          mermaid.initialize({
            flowchart: { htmlLabels: false },
            securityLevel: "strict",
            startOnLoad: false,
            theme: "base",
            themeVariables: {
              fontFamily: "Inter, Arial, sans-serif",
              lineColor: "#44546f",
              mainBkg: "#ffffff",
              nodeBorder: "#d8dee8",
              primaryColor: "#f7f8fa",
              primaryTextColor: "#172b4d",
            },
          });
          mermaidInitialized = true;
        }
        const rendered = await mermaid.render(
          `graph-run-${reactId}-${view.graph_key}`,
          view.mermaid,
        );
        if (!cancelled) {
          setSvg(rendered.svg);
          setError(null);
          setSelectedMermaidNodeId(null);
        }
      } catch (caught) {
        if (!cancelled) {
          setSvg("");
          setError(
            caught instanceof Error
              ? caught.message
              : "Не удалось отрендерить граф.",
          );
        }
      }
    }
    void renderGraph();
    return () => {
      cancelled = true;
    };
  }, [reactId, view.graph_key, view.mermaid]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !svg) {
      return;
    }
    const graphNodes = [...container.querySelectorAll<SVGGElement>("g.node")];
    for (const element of graphNodes) {
      const mermaidId = resolveSvgNodeId(element, view.nodes);
      if (!mermaidId) {
        continue;
      }
      element.dataset.graphNodeId = mermaidId;
      element.setAttribute("role", "button");
      element.setAttribute("tabindex", "0");
      element.setAttribute("aria-label", `Открыть данные узла ${mermaidId}`);
    }
  }, [selectedMermaidNodeId, svg, view.nodes]);

  useEffect(() => {
    if (!selectedMermaidNodeId) {
      return;
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setSelectedMermaidNodeId(null);
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selectedMermaidNodeId]);

  function handleGraphClick(event: React.MouseEvent<HTMLDivElement>) {
    const element = (event.target as Element | null)?.closest<SVGGElement>(
      "g[data-graph-node-id], g.node",
    );
    const nodeId =
      element?.dataset.graphNodeId ??
      (element ? resolveSvgNodeId(element, view.nodes) : null);
    if (nodeId) {
      setSelectedMermaidNodeId(nodeId);
    }
  }

  function handleGraphKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key !== "Enter" && event.key !== " ") {
      return;
    }
    const element = (event.target as Element | null)?.closest<SVGGElement>(
      "g[data-graph-node-id], g.node",
    );
    const nodeId =
      element?.dataset.graphNodeId ??
      (element ? resolveSvgNodeId(element, view.nodes) : null);
    if (nodeId) {
      event.preventDefault();
      setSelectedMermaidNodeId(nodeId);
    }
  }

  return (
    <section className="rounded-[12px] border border-black/10 p-4">
      <div className="mb-3 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <h4 className="text-sm font-bold text-ink">
          {getGraphLabel(view.graph_key)}
        </h4>
        <p className="text-xs text-ink/45">
          Выполнено узлов: {view.executed_node_ids.length}. Пройдено ребер:{" "}
          {view.executed_edge_ids.length}. Выбрано переходов:{" "}
          {view.selected_edge_ids.length}.
        </p>
      </div>
      <div className="mb-3 flex flex-wrap gap-3 text-xs text-ink/55">
        <span className="inline-flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full border-2 border-[#0c66e4] bg-[#e9f2ff]" />
          выполненный узел
        </span>
        <span className="inline-flex items-center gap-2">
          <span className="h-0.5 w-8 bg-[#6b778c]" />
          пройденное ребро
        </span>
        <span className="inline-flex items-center gap-2">
          <span className="h-1 w-8 bg-[#0c66e4]" />
          выбранное условие
        </span>
      </div>
      {error ? (
        <p className="rounded-[10px] bg-ember/10 px-3 py-2 text-sm text-ember">
          {error}
        </p>
      ) : (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
          <div
            className="overflow-auto rounded-[10px] bg-[#f7f8fa] p-4 [&_g[data-graph-node-id]]:cursor-pointer [&_g[data-graph-node-id]:focus-visible_*]:outline [&_g[data-graph-node-id]:focus-visible_*]:outline-2 [&_g[data-graph-node-id]:focus-visible_*]:outline-[#0c66e4] [&_g[data-graph-node-id]:hover_*]:brightness-95 [&_svg]:mx-auto [&_svg]:max-w-full"
            dangerouslySetInnerHTML={{ __html: svg }}
            onClick={handleGraphClick}
            onKeyDown={handleGraphKeyDown}
            ref={containerRef}
          />
          <GraphNodeSidePanel
            graphNode={selectedGraphNode ?? null}
            llmRequests={nodeLlmRequests}
            onClose={() => setSelectedMermaidNodeId(null)}
            runNode={selectedRunNode}
          />
        </div>
      )}

      {transitions.length > 0 ? (
        <div className="mt-4">
          <h5 className="text-sm font-bold text-ink">Выбранные переходы</h5>
          <TransitionList detail={{ ...detail, transitions }} />
        </div>
      ) : null}
    </section>
  );
}

function resolveSvgNodeId(
  element: Element,
  nodes: GraphRunGraphViewRead["nodes"],
) {
  const nodeIds = nodes.map((node) => node.mermaid_id).sort(
    (left, right) => right.length - left.length,
  );
  const rawValues = [
    element.getAttribute("data-id"),
    element.id,
    element.getAttribute("id"),
  ].filter((value): value is string => Boolean(value));

  for (const rawValue of rawValues) {
    for (const nodeId of nodeIds) {
      if (
        rawValue === nodeId ||
        rawValue === `flowchart-${nodeId}` ||
        rawValue.includes(`-${nodeId}-`) ||
        rawValue.endsWith(`-${nodeId}`)
      ) {
        return nodeId;
      }
    }
  }
  return null;
}

function GraphNodeSidePanel({
  graphNode,
  llmRequests,
  onClose,
  runNode,
}: {
  graphNode: GraphRunGraphViewRead["nodes"][number] | null;
  llmRequests: LLMRequestItem[];
  onClose: () => void;
  runNode: GraphRunNodeRead | null;
}) {
  if (!graphNode) {
    return (
      <aside className="rounded-[12px] border border-dashed border-black/10 bg-white p-4 text-sm text-ink/55">
        Выберите узел на схеме, чтобы открыть входные и выходные данные.
      </aside>
    );
  }

  return (
    <aside className="rounded-[12px] border border-black/10 bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.12em] text-ink/45">
            Узел графа
          </p>
          <h5 className="mt-1 text-base font-bold text-ink">
            {graphNode.node_name}
          </h5>
        </div>
        <button className="ui-button-secondary" onClick={onClose} type="button">
          Закрыть
        </button>
      </div>

      {!runNode ? (
        <p className="mt-4 rounded-[10px] bg-[#f7f8fa] px-3 py-2 text-sm text-ink/60">
          Узел не выполнялся в этом run.
        </p>
      ) : (
        <>
          <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
            <StatusPill status={runNode.status} />
            <span className="text-ink/55">{formatLatency(runNode.latency_ms)}</span>
          </div>
          <p className="mt-2 text-xs leading-5 text-ink/55">
            {getGraphLabel(runNode.graph_key)} /{" "}
            {runNode.namespace ?? "namespace не указан"}
          </p>
          {runNode.error_message ? (
            <p className="mt-3 rounded-[10px] bg-ember/10 px-3 py-2 text-sm text-ember">
              {runNode.error_message}
            </p>
          ) : null}
          <Preview title="Вход узла" value={runNode.input_preview} />
          <Preview title="Выход узла" value={runNode.result_preview} />
          <h5 className="mt-4 text-sm font-bold text-ink">
            LLM-вызовы узла
          </h5>
          <LLMRequestList items={llmRequests} />
        </>
      )}
    </aside>
  );
}

function TransitionList({ detail }: { detail: Pick<GraphRunDetailRead, "transitions"> }) {
  return (
    <div className="mt-3 space-y-2">
      {detail.transitions.map((transition) => (
        <article
          className="rounded-[12px] border border-black/10 p-3 text-sm"
          key={transition.id}
        >
          <div className="font-semibold text-ink">
            {transition.source_node ?? "source"} -&gt;{" "}
            {transition.target_nodes.join(", ")}
          </div>
          <div className="mt-1 text-ink/60">
            {transition.condition ?? "condition"}:{" "}
            {transition.reason ?? transition.selected.join(", ")}
          </div>
        </article>
      ))}
    </div>
  );
}

function LLMRequestList({ items }: { items: LLMRequestItem[] }) {
  return (
    <div className="mt-3 space-y-2">
      {items.length === 0 ? (
        <p className="text-sm text-ink/55">LLM-вызовов нет.</p>
      ) : (
        items.map((item) => (
          <article
            className="rounded-[12px] border border-black/10 p-3 text-sm"
            key={item.id}
          >
            <div className="font-semibold text-ink">
              {getAgentKeyLabel(item.agent_key)} /{" "}
              {item.graph_node_name ?? "узел не указан"}
            </div>
            <div className="mt-1 text-ink/60">
              {getProviderKindLabel(item.provider_kind)} {item.model} /{" "}
              {formatLatency(item.latency_ms)} /{" "}
              {formatCurrencyUsd(item.estimated_cost_usd)}
            </div>
          </article>
        ))
      )}
    </div>
  );
}

function Preview({ title, value }: { title: string; value: unknown }) {
  return (
    <div className="mt-3">
      <h4 className="mb-2 text-sm font-bold text-ink">{title}</h4>
      <pre className="max-h-80 overflow-auto rounded-[12px] border border-black/10 bg-[#0f172a] p-3 text-xs leading-5 text-white/90">
        {formatJson(value)}
      </pre>
    </div>
  );
}
