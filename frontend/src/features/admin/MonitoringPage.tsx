import { useEffect, useEffectEvent, useState } from "react";

import {
  adminApi,
  type AuditPageRead,
  type MonitoringActivityRead,
  type MonitoringLLMRead,
  type MonitoringRange,
  type MonitoringSummaryRead,
} from "@/api/adminApi";
import { LoadingSpinner } from "@/shared/components/LoadingSpinner";
import { TrendChart } from "@/shared/components/TrendChart";
import { getApiErrorMessage } from "@/shared/lib/apiError";
import {
  formatCurrencyUsd,
  formatDateTimeFull,
  formatPercent,
  getAgentKeyLabel,
  getEntityTypeLabel,
  getEventTypeLabel,
  getMonitoringRangeLabel,
  getProviderKindLabel,
} from "@/shared/lib/locale";

const RANGE_OPTIONS: MonitoringRange[] = ["24h", "7d", "30d", "90d"];
const SERIES_COLORS = ["#d4693b", "#2c5748", "#2f70c0", "#8a5cf6", "#c46b8f"];

export default function MonitoringPage() {
  const [range, setRange] = useState<MonitoringRange>("7d");
  const [summary, setSummary] = useState<MonitoringSummaryRead | null>(null);
  const [activity, setActivity] = useState<MonitoringActivityRead | null>(null);
  const [llm, setLlm] = useState<MonitoringLLMRead | null>(null);
  const [audit, setAudit] = useState<AuditPageRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadData(activeRange: MonitoringRange) {
    try {
      setLoading(true);
      setError(null);
      const [loadedSummary, loadedActivity, loadedLlm, loadedAudit] =
        await Promise.all([
          adminApi.getMonitoringSummary(activeRange),
          adminApi.getMonitoringActivity(activeRange),
          adminApi.getMonitoringLlm(activeRange),
          adminApi.getAudit(activeRange),
        ]);
      setSummary(loadedSummary);
      setActivity(loadedActivity);
      setLlm(loadedLlm);
      setAudit(loadedAudit);
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось загрузить данные мониторинга."));
    } finally {
      setLoading(false);
    }
  }

  const onLoadData = useEffectEvent(loadData);

  useEffect(() => {
    void onLoadData(range);
  }, [range]); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading && (!summary || !activity || !llm || !audit)) {
    return <LoadingSpinner label="Загрузка мониторинга" />;
  }

  const activitySeries = [
    {
      label: "События",
      color: SERIES_COLORS[0],
      points: (activity?.buckets ?? []).map((bucket) => ({
        label: bucket.day,
        value: bucket.events_total,
      })),
    },
  ];

  const providerKinds = Array.from(
    new Set((llm?.daily ?? []).flatMap((item) => Object.keys(item.providers))),
  );
  const llmSeries = providerKinds.map((providerKind, index) => ({
    label: getProviderKindLabel(providerKind),
    color: SERIES_COLORS[index % SERIES_COLORS.length],
    points: (llm?.daily ?? []).map((item) => ({
      label: item.day,
      value: item.providers[providerKind] ?? 0,
    })),
  }));

  return (
    <section className="space-y-6">
      <header className="glass-panel rounded-[28px] border border-black/10 p-6 shadow-panel">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-ember">
              Мониторинг
            </p>
            <h3 className="mt-2 text-2xl font-extrabold text-ink sm:text-3xl">
              Прозрачность системы
            </h3>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-ink/70">
              Следите за использованием платформы, административной активностью
              и работой провайдеров в выбранном временном окне.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {RANGE_OPTIONS.map((item) => (
              <button
                key={item}
                className={item === range ? "ui-button-primary" : "ui-button-secondary"}
                onClick={() => setRange(item)}
                type="button"
              >
                {getMonitoringRangeLabel(item)}
              </button>
            ))}
          </div>
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

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <article className="glass-panel rounded-[24px] border border-black/10 p-5 shadow-panel">
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-ink/45">
            Пользователи
          </p>
          <p className="mt-3 text-3xl font-extrabold text-ink">
            {summary?.all_time.users_total ?? 0}
          </p>
          <p className="mt-2 text-sm text-ink/60">
            Активных аккаунтов: {summary?.all_time.active_users_total ?? 0}
          </p>
        </article>
        <article className="glass-panel rounded-[24px] border border-black/10 p-5 shadow-panel">
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-ink/45">
            Задачи
          </p>
          <p className="mt-3 text-3xl font-extrabold text-ink">
            {summary?.all_time.tasks_total ?? 0}
          </p>
          <p className="mt-2 text-sm text-ink/60">
            Проверок выполнено: {summary?.all_time.validations_total ?? 0}
          </p>
        </article>
        <article className="glass-panel rounded-[24px] border border-black/10 p-5 shadow-panel">
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-ink/45">
            Сообщения
          </p>
          <p className="mt-3 text-3xl font-extrabold text-ink">
            {summary?.all_time.messages_total ?? 0}
          </p>
          <p className="mt-2 text-sm text-ink/60">
            Предложений: {summary?.all_time.proposals_total ?? 0}
          </p>
        </article>
        <article className="glass-panel rounded-[24px] border border-black/10 p-5 shadow-panel">
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-ink/45">
            Окно активности
          </p>
          <p className="mt-3 text-3xl font-extrabold text-ink">
            {summary?.range_metrics.audit_events_total ?? 0}
          </p>
          <p className="mt-2 text-sm text-ink/60">
            Активных участников: {summary?.range_metrics.active_users ?? 0}
          </p>
        </article>
        <article className="glass-panel rounded-[24px] border border-black/10 p-5 shadow-panel">
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-ink/45">
            LLM-запросы
          </p>
          <p className="mt-3 text-3xl font-extrabold text-ink">
            {summary?.range_metrics.llm_requests_total ?? 0}
          </p>
          <p className="mt-2 text-sm text-ink/60">
            Ошибки: {formatPercent(summary?.range_metrics.llm_error_rate ?? 0)}
          </p>
        </article>
        <article className="glass-panel rounded-[24px] border border-black/10 p-5 shadow-panel">
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-ink/45">
            Производительность
          </p>
          <p className="mt-3 text-3xl font-extrabold text-ink">
            {summary?.range_metrics.avg_llm_latency_ms
              ? `${summary.range_metrics.avg_llm_latency_ms.toFixed(0)} мс`
              : "н/д"}
          </p>
          <p className="mt-2 text-sm text-ink/60">
            Оценочная стоимость: {formatCurrencyUsd(summary?.range_metrics.estimated_llm_cost_usd ?? null)}
          </p>
        </article>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <article className="glass-panel rounded-[28px] border border-black/10 p-6 shadow-panel">
          <div className="mb-4">
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-ember">
              Активность
            </p>
            <h3 className="mt-2 text-2xl font-extrabold text-ink">
              Ежедневная операционная активность
            </h3>
          </div>
          <TrendChart
            emptyLabel="В выбранном диапазоне событий аудита пока нет."
            series={activitySeries}
          />
        </article>

        <article className="glass-panel rounded-[28px] border border-black/10 p-6 shadow-panel">
          <div className="mb-4">
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-ember">
              Использование LLM
            </p>
            <h3 className="mt-2 text-2xl font-extrabold text-ink">
              Ежедневная нагрузка на провайдеров
            </h3>
          </div>
          <TrendChart
            emptyLabel="В выбранном диапазоне LLM-запросов пока нет."
            series={llmSeries}
          />
        </article>
      </div>

      <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <article className="glass-panel rounded-[28px] border border-black/10 p-6 shadow-panel">
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-ember">
            Лидеры
          </p>
          <h3 className="mt-2 text-2xl font-extrabold text-ink">
            Самые активные участники и действия
          </h3>
          <div className="mt-5 grid gap-4 md:grid-cols-2">
            <div className="rounded-[24px] border border-black/10 bg-white/70 p-4">
              <p className="text-sm font-bold text-ink">Активные пользователи</p>
              <div className="mt-3 space-y-3">
                {(activity?.top_actors ?? []).map((actor) => (
                  <div
                    key={`${actor.user_id ?? "system"}-${actor.full_name}`}
                    className="flex items-center justify-between gap-3 text-sm"
                  >
                    <span className="text-ink/70">{actor.full_name}</span>
                    <span className="font-bold text-ink">{actor.event_count}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="rounded-[24px] border border-black/10 bg-white/70 p-4">
              <p className="text-sm font-bold text-ink">Частые действия</p>
              <div className="mt-3 space-y-3">
                {(activity?.top_actions ?? []).map((item) => (
                  <div
                    key={item.event_type}
                    className="flex items-center justify-between gap-3 text-sm"
                  >
                    <span className="text-ink/70">
                      {getEventTypeLabel(item.event_type)}
                    </span>
                    <span className="font-bold text-ink">{item.count}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </article>

        <article className="glass-panel rounded-[28px] border border-black/10 p-6 shadow-panel">
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-ember">
            Структура
          </p>
          <h3 className="mt-2 text-2xl font-extrabold text-ink">
            Распределение по провайдерам
          </h3>
          <div className="mt-5 space-y-3">
            {(llm?.provider_breakdown ?? []).map((item) => (
              <div
                key={item.provider_kind}
                className="rounded-[22px] border border-black/10 bg-white/70 p-4"
              >
                <div className="flex items-center justify-between gap-3 text-sm font-semibold text-ink">
                  <span>{getProviderKindLabel(item.provider_kind)}</span>
                  <span>{item.request_count}</span>
                </div>
                <div className="mt-3 h-2 rounded-full bg-black/6">
                  <div
                    className="h-2 rounded-full bg-ember"
                    style={{
                      width: `${llm?.requests_total ? (item.request_count / llm.requests_total) * 100 : 0}%`,
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </article>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <article className="glass-panel rounded-[28px] border border-black/10 p-6 shadow-panel">
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-ember">
            Сбои
          </p>
          <h3 className="mt-2 text-2xl font-extrabold text-ink">
            Последние ошибки LLM
          </h3>
          <div className="mt-5 space-y-3">
            {(llm?.recent_failures ?? []).length === 0 ? (
              <p className="rounded-[24px] border border-dashed border-black/10 bg-white/60 px-4 py-6 text-sm text-ink/55">
                В этом окне не было неудачных LLM-вызовов.
              </p>
            ) : (
              (llm?.recent_failures ?? []).map((item) => (
                <article
                  key={item.id}
                  className="rounded-[24px] border border-black/10 bg-white/70 p-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-bold text-ink">
                        {getProviderKindLabel(item.provider_kind)} · {item.model}
                      </p>
                      <p className="text-xs uppercase tracking-[0.14em] text-ink/45">
                        {item.actor_name} · {item.agent_key ? getAgentKeyLabel(item.agent_key) : "Проверка провайдера"}
                      </p>
                    </div>
                    <span className="text-xs text-ink/45">
                      {formatDateTimeFull(item.created_at)}
                    </span>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-ink/70">
                    {item.error_message ?? "Неизвестная ошибка"}
                  </p>
                </article>
              ))
            )}
          </div>
        </article>

        <article className="glass-panel rounded-[28px] border border-black/10 p-6 shadow-panel">
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-ember">
            Аудит
          </p>
          <h3 className="mt-2 text-2xl font-extrabold text-ink">
            Последние события аудита
          </h3>
          <div className="mt-5 space-y-3">
            {(audit?.items ?? []).map((item) => (
              <article
                key={item.id}
                className="rounded-[24px] border border-black/10 bg-white/70 p-4"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-bold text-ink">
                      {getEventTypeLabel(item.event_type)}
                    </p>
                    <p className="text-xs uppercase tracking-[0.14em] text-ink/45">
                      {item.actor_name} · {getEntityTypeLabel(item.entity_type)}
                    </p>
                  </div>
                  <span className="text-xs text-ink/45">
                    {formatDateTimeFull(item.created_at)}
                  </span>
                </div>
                {item.entity_id ? (
                  <p className="mt-3 text-sm text-ink/65">Объект: {item.entity_id}</p>
                ) : null}
              </article>
            ))}
          </div>
        </article>
      </div>
    </section>
  );
}
