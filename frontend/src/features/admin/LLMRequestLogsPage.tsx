import { useEffect, useEffectEvent, useState } from "react";

import {
  adminApi,
  type LLMRequestLogPageRead,
  type LLMRequestStatus,
  type LLMRuntimeSettingsRead,
  type MonitoringRange,
  type PromptLogMode,
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

type StatusFilter = "all" | LLMRequestStatus;

const STATUS_OPTIONS: Array<{ label: string; value: StatusFilter }> = [
  { value: "all", label: "Все статусы" },
  { value: "success", label: "Успешные" },
  { value: "error", label: "Ошибки" },
];

const LOG_MODE_OPTIONS: Array<{
  description: string;
  label: string;
  value: PromptLogMode;
}> = [
  {
    value: "full",
    label: "Запросы и ответы",
    description: "Сохраняются метаданные, prompt и текст ответа.",
  },
  {
    value: "metadata_only",
    label: "Только метаданные",
    description: "Сохраняются статусы, токены, стоимость и задержка.",
  },
  {
    value: "disabled",
    label: "Выключен",
    description: "Новые вызовы LLM не попадают в журнал.",
  },
];

const REQUEST_KIND_LABELS: Record<string, string> = {
  chat: "Чат",
  provider_test: "Проверка провайдера",
  vision_alt_text: "Распознавание вложения",
};

function getRequestKindLabel(value: string) {
  return REQUEST_KIND_LABELS[value] ?? value.replaceAll("_", " ");
}

function stringifyMessages(messages: Array<Record<string, unknown>> | null) {
  if (!messages || messages.length === 0) {
    return "Содержимое запроса не сохранено.";
  }
  return JSON.stringify(messages, null, 2);
}

function getResponseText(item: LLMRequestLogPageRead["items"][number]) {
  if (item.response_text) {
    return item.response_text;
  }
  if (item.status === "error" && item.error_message) {
    return item.error_message;
  }
  return "Содержимое ответа не сохранено.";
}

function formatTokens(item: LLMRequestLogPageRead["items"][number]) {
  if (item.total_tokens === null) {
    return "н/д";
  }
  return `${item.total_tokens} токенов`;
}

export default function LLMRequestLogsPage() {
  const [range, setRange] = useState<MonitoringRange>("7d");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [page, setPage] = useState(1);
  const [settings, setSettings] = useState<LLMRuntimeSettingsRead | null>(null);
  const [logs, setLogs] = useState<LLMRequestLogPageRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingMode, setSavingMode] = useState<PromptLogMode | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadData(
    activeRange: MonitoringRange,
    activeStatus: StatusFilter,
    activePage: number,
  ) {
    try {
      setLoading(true);
      setError(null);
      const [loadedSettings, loadedLogs] = await Promise.all([
        adminApi.getLlmRuntimeSettings(),
        adminApi.getLlmRequestLogs(
          activeRange,
          activePage,
          activeStatus === "all" ? undefined : activeStatus,
        ),
      ]);
      setSettings(loadedSettings);
      setLogs(loadedLogs);
    } catch (caught) {
      setError(
        getApiErrorMessage(caught, "Не удалось загрузить журнал LLM-запросов."),
      );
    } finally {
      setLoading(false);
    }
  }

  const onLoadData = useEffectEvent(loadData);

  useEffect(() => {
    void onLoadData(range, statusFilter, page);
  }, [range, statusFilter, page]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleModeChange(promptLogMode: PromptLogMode) {
    if (settings?.prompt_log_mode === promptLogMode) {
      return;
    }

    try {
      setSavingMode(promptLogMode);
      setError(null);
      const updatedSettings =
        await adminApi.updateLlmRuntimeSettings(promptLogMode);
      setSettings(updatedSettings);
      setLogs((current) =>
        current
          ? { ...current, prompt_log_mode: updatedSettings.prompt_log_mode }
          : current,
      );
    } catch (caught) {
      setError(
        getApiErrorMessage(
          caught,
          "Не удалось обновить режим LLM-мониторинга.",
        ),
      );
    } finally {
      setSavingMode(null);
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

  if (loading && !logs) {
    return <LoadingSpinner label="Загрузка журнала LLM-запросов" />;
  }

  const activeLogMode = settings?.prompt_log_mode ?? logs?.prompt_log_mode;
  const activeLogModeOption = LOG_MODE_OPTIONS.find(
    (item) => item.value === activeLogMode,
  );
  const totalPages = logs
    ? Math.max(1, Math.ceil(logs.total / logs.page_size))
    : 1;

  return (
    <section className="space-y-6">
      <header className="glass-panel rounded-[28px] border border-black/10 p-6 shadow-panel">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-ember">
              LLM-мониторинг
            </p>
            <h3 className="mt-2 text-2xl font-extrabold text-ink sm:text-3xl">
              Журнал запросов и ответов
            </h3>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-ink/70">
              Последние вызовы модельного слоя с контекстом агента, токенами,
              задержкой и сохраненным содержимым.
            </p>
          </div>
          <button
            className="ui-button-secondary"
            disabled={loading}
            onClick={() => void loadData(range, statusFilter, page)}
            type="button"
          >
            Обновить
          </button>
        </div>

        {error ? (
          <p
            aria-live="polite"
            className="mt-4 rounded-2xl bg-ember/10 px-4 py-3 text-sm text-ember"
          >
            {error}
          </p>
        ) : null}
      </header>

      <section className="glass-panel rounded-[28px] border border-black/10 p-6 shadow-panel">
        <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-ember">
              Режим записи
            </p>
            <h3 className="mt-2 text-2xl font-extrabold text-ink">
              Управление LLM-мониторингом
            </h3>
            <p className="mt-3 max-w-2xl text-sm leading-7 text-ink/70">
              {activeLogModeOption?.description ??
                "Режим мониторинга пока не загружен."}
            </p>
          </div>
          <div
            aria-label="Режим LLM-мониторинга"
            className="flex flex-wrap gap-2"
            role="radiogroup"
          >
            {LOG_MODE_OPTIONS.map((item) => (
              <button
                key={item.value}
                aria-checked={activeLogMode === item.value}
                className={
                  activeLogMode === item.value
                    ? "ui-button-primary"
                    : "ui-button-secondary"
                }
                disabled={savingMode !== null}
                onClick={() => void handleModeChange(item.value)}
                role="radio"
                type="button"
              >
                {savingMode === item.value ? "Сохраняем..." : item.label}
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="glass-panel rounded-[28px] border border-black/10 p-6 shadow-panel">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
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

        <div className="mt-5 space-y-4">
          {(logs?.items ?? []).length === 0 ? (
            <p className="rounded-[20px] border border-dashed border-black/10 bg-white/60 px-4 py-6 text-sm text-ink/55">
              В выбранном окне LLM-запросов нет.
            </p>
          ) : (
            (logs?.items ?? []).map((item) => (
              <article
                key={item.id}
                className="rounded-[24px] border border-black/10 bg-white/75 p-4"
              >
                <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={
                          item.status === "success"
                            ? "rounded-full bg-pine/15 px-3 py-1 text-xs font-bold uppercase tracking-[0.14em] text-pine"
                            : "rounded-full bg-ember/12 px-3 py-1 text-xs font-bold uppercase tracking-[0.14em] text-ember"
                        }
                      >
                        {item.status === "success" ? "Успешно" : "Ошибка"}
                      </span>
                      <span className="rounded-full bg-black/5 px-3 py-1 text-xs font-bold uppercase tracking-[0.14em] text-ink/55">
                        {getRequestKindLabel(item.request_kind)}
                      </span>
                    </div>
                    <h3 className="text-xl font-extrabold text-ink">
                      {getProviderKindLabel(item.provider_kind)} / {item.model}
                    </h3>
                    <p className="text-sm text-ink/65">
                      {item.agent_key
                        ? getAgentKeyLabel(item.agent_key)
                        : "Системная проверка"}{" "}
                      / {item.actor_name}
                    </p>
                  </div>
                  <dl className="grid gap-3 text-sm text-ink/70 sm:grid-cols-2 xl:min-w-[420px] xl:grid-cols-4">
                    <div>
                      <dt className="font-semibold text-ink/45">Время</dt>
                      <dd>{formatDateTimeWithSeconds(item.created_at)}</dd>
                    </div>
                    <div>
                      <dt className="font-semibold text-ink/45">Задержка</dt>
                      <dd>
                        {item.latency_ms ? `${item.latency_ms} мс` : "н/д"}
                      </dd>
                    </div>
                    <div>
                      <dt className="font-semibold text-ink/45">Токены</dt>
                      <dd>{formatTokens(item)}</dd>
                    </div>
                    <div>
                      <dt className="font-semibold text-ink/45">Стоимость</dt>
                      <dd>{formatCurrencyUsd(item.estimated_cost_usd)}</dd>
                    </div>
                  </dl>
                </div>

                <div className="mt-4 grid gap-4 xl:grid-cols-2">
                  <div>
                    <p className="mb-2 text-sm font-bold text-ink">Запрос</p>
                    <pre className="max-h-80 overflow-auto rounded-[16px] border border-black/10 bg-[#0f172a] p-4 text-xs leading-6 text-white/90">
                      {stringifyMessages(item.request_messages)}
                    </pre>
                  </div>
                  <div>
                    <p className="mb-2 text-sm font-bold text-ink">Ответ</p>
                    <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-[16px] border border-black/10 bg-[#f7f8fa] p-4 text-xs leading-6 text-ink/80">
                      {getResponseText(item)}
                    </pre>
                  </div>
                </div>

                {item.task_id || item.project_id ? (
                  <p className="mt-4 text-xs uppercase tracking-[0.14em] text-ink/45">
                    Проект: {item.project_id ?? "н/д"} / Задача:{" "}
                    {item.task_id ?? "н/д"}
                  </p>
                ) : null}
              </article>
            ))
          )}
        </div>

        <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-ink/60">
            Всего записей: {logs?.total ?? 0}. Страница {page} из {totalPages}.
          </p>
          <div className="flex gap-2">
            <button
              className="ui-button-secondary"
              disabled={page <= 1}
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              type="button"
            >
              Назад
            </button>
            <button
              className="ui-button-secondary"
              disabled={page >= totalPages}
              onClick={() =>
                setPage((current) => Math.min(totalPages, current + 1))
              }
              type="button"
            >
              Вперед
            </button>
          </div>
        </div>
      </section>
    </section>
  );
}
