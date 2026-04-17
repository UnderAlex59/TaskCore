import { useEffect, useEffectEvent, useState } from "react";

import {
  adminApi,
  type AgentOverrideRead,
  type ProviderConfigPayload,
  type ProviderConfigRead,
  type ProviderKind,
} from "@/api/adminApi";
import { LoadingSpinner } from "@/shared/components/LoadingSpinner";
import { getApiErrorMessage } from "@/shared/lib/apiError";
import {
  getAgentKeyLabel,
  getProviderKindLabel,
} from "@/shared/lib/locale";

type ProviderFormState = {
  base_url: string;
  enabled: boolean;
  input_cost_per_1k_tokens: string;
  model: string;
  name: string;
  output_cost_per_1k_tokens: string;
  provider_kind: ProviderKind;
  secret: string;
  temperature: string;
};

type OverrideDraft = {
  enabled: boolean;
  provider_config_id: string;
};

const PROVIDER_OPTIONS: Array<{ description: string; value: ProviderKind }> = [
  { value: "openai", description: "Облачный API OpenAI" },
  { value: "ollama", description: "Локальный сервер Ollama" },
  { value: "openrouter", description: "Профиль OpenRouter" },
  { value: "gigachat", description: "GigaChat с обменом токенов" },
  { value: "openai_compatible", description: "Совместимый с OpenAI API сервер" },
];

const AGENT_OPTIONS = [
  { key: "qa", label: "Агент вопросов" },
  { key: "change-tracker", label: "Трекер изменений" },
];

const DEFAULT_MODELS: Record<ProviderKind, string> = {
  openai: "gpt-4o-mini",
  ollama: "llama3.1",
  openrouter: "openai/gpt-4o-mini",
  gigachat: "GigaChat",
  openai_compatible: "model-name",
};

const DEFAULT_BASE_URLS: Partial<Record<ProviderKind, string>> = {
  openai: "https://api.openai.com/v1",
  ollama: "http://localhost:11434",
  openrouter: "https://openrouter.ai/api/v1",
  gigachat: "https://gigachat.devices.sberbank.ru/api/v1",
};

const EMPTY_FORM: ProviderFormState = {
  name: "",
  provider_kind: "openai",
  base_url: DEFAULT_BASE_URLS.openai ?? "",
  model: DEFAULT_MODELS.openai,
  temperature: "0.2",
  enabled: false,
  input_cost_per_1k_tokens: "",
  output_cost_per_1k_tokens: "",
  secret: "",
};

function toNullableNumber(value: string) {
  if (!value.trim()) {
    return null;
  }
  return Number(value);
}

function toPayload(form: ProviderFormState): ProviderConfigPayload {
  return {
    name: form.name.trim(),
    provider_kind: form.provider_kind,
    base_url: form.base_url.trim() || null,
    model: form.model.trim(),
    temperature: Number(form.temperature),
    enabled: form.enabled,
    input_cost_per_1k_tokens: toNullableNumber(form.input_cost_per_1k_tokens),
    output_cost_per_1k_tokens: toNullableNumber(form.output_cost_per_1k_tokens),
    ...(form.secret.trim() ? { secret: form.secret.trim() } : {}),
  };
}

function toFormState(provider: ProviderConfigRead): ProviderFormState {
  return {
    name: provider.name,
    provider_kind: provider.provider_kind,
    base_url: provider.base_url,
    model: provider.model,
    temperature: String(provider.temperature),
    enabled: provider.enabled,
    input_cost_per_1k_tokens: provider.input_cost_per_1k_tokens ? String(provider.input_cost_per_1k_tokens) : "",
    output_cost_per_1k_tokens: provider.output_cost_per_1k_tokens ? String(provider.output_cost_per_1k_tokens) : "",
    secret: "",
  };
}

function buildOverrideDrafts(
  providers: ProviderConfigRead[],
  overrides: AgentOverrideRead[],
): Record<string, OverrideDraft> {
  const overrideByAgent = new Map(overrides.map((item) => [item.agent_key, item]));
  const fallbackProviderId = providers[0]?.id ?? "";
  return Object.fromEntries(
    AGENT_OPTIONS.map((item) => {
      const override = overrideByAgent.get(item.key);
      return [
        item.key,
        {
          provider_config_id: override?.provider_config_id ?? fallbackProviderId,
          enabled: override?.enabled ?? false,
        },
      ];
    }),
  );
}

export default function ProviderSettingsPage() {
  const [providers, setProviders] = useState<ProviderConfigRead[]>([]);
  const [overrideDrafts, setOverrideDrafts] = useState<Record<string, OverrideDraft>>({});
  const [form, setForm] = useState<ProviderFormState>(EMPTY_FORM);
  const [editingProviderId, setEditingProviderId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testingProviderId, setTestingProviderId] = useState<string | null>(null);
  const [settingDefaultId, setSettingDefaultId] = useState<string | null>(null);
  const [savingOverrideKey, setSavingOverrideKey] = useState<string | null>(null);
  const [testMessages, setTestMessages] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  async function loadData() {
    try {
      setLoading(true);
      setError(null);
      const [loadedProviders, loadedOverrides] = await Promise.all([
        adminApi.listProviders(),
        adminApi.listOverrides(),
      ]);
      setProviders(loadedProviders);
      setOverrideDrafts(buildOverrideDrafts(loadedProviders, loadedOverrides));
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось загрузить настройки провайдеров."));
    } finally {
      setLoading(false);
    }
  }

  const onLoadData = useEffectEvent(loadData);

  // Effect Events must stay out of deps, otherwise the load effect re-triggers itself.
  useEffect(() => {
    void onLoadData();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    try {
      setSaving(true);
      setError(null);
      if (editingProviderId) {
        await adminApi.updateProvider(editingProviderId, toPayload(form));
      } else {
        await adminApi.createProvider(toPayload(form));
      }
      setEditingProviderId(null);
      setForm(EMPTY_FORM);
      await loadData();
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось сохранить профиль провайдера."));
    } finally {
      setSaving(false);
    }
  }

  async function handleTest(providerId: string) {
    try {
      setTestingProviderId(providerId);
      const result = await adminApi.testProvider(providerId);
      setTestMessages((current) => ({
        ...current,
        [providerId]: `${result.ok ? "Успешно" : "Ошибка"}${result.latency_ms ? ` · ${result.latency_ms} мс` : ""} · ${result.message}`,
      }));
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось проверить профиль провайдера."));
    } finally {
      setTestingProviderId(null);
    }
  }

  async function handleSetDefault(providerId: string) {
    try {
      setSettingDefaultId(providerId);
      await adminApi.setDefaultProvider(providerId);
      await loadData();
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось обновить провайдера по умолчанию."));
    } finally {
      setSettingDefaultId(null);
    }
  }

  async function handleSaveOverride(agentKey: string) {
    const draft = overrideDrafts[agentKey];
    if (!draft?.provider_config_id) {
      setError("Выберите провайдера перед сохранением маршрутизации.");
      return;
    }

    try {
      setSavingOverrideKey(agentKey);
      await adminApi.updateOverride(agentKey, draft.provider_config_id, draft.enabled);
      await loadData();
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось сохранить маршрутизацию агента."));
    } finally {
      setSavingOverrideKey(null);
    }
  }

  function startEdit(provider: ProviderConfigRead) {
    setEditingProviderId(provider.id);
    setForm(toFormState(provider));
  }

  function resetForm() {
    setEditingProviderId(null);
    setForm(EMPTY_FORM);
  }

  if (loading) {
    return <LoadingSpinner label="Загрузка провайдеров" />;
  }

  return (
    <section className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <form className="glass-panel space-y-4 rounded-[28px] border border-black/10 p-6 shadow-panel" onSubmit={handleSubmit}>
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.16em] text-ember">Профиль провайдера</p>
              <h3 className="mt-2 text-2xl font-extrabold text-ink">
                {editingProviderId ? "Редактирование рабочего профиля" : "Создание нового профиля"}
              </h3>
            </div>
            {editingProviderId ? (
              <button className="ui-button-secondary" onClick={resetForm} type="button">
                Отмена
              </button>
            ) : null}
          </div>

          {error ? (
            <p aria-live="polite" className="rounded-2xl bg-ember/10 px-4 py-3 text-sm text-ember">
              {error}
            </p>
          ) : null}

          <div className="grid gap-4 md:grid-cols-2">
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-ink/70">Название профиля</span>
              <input
                className="ui-field"
                onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
                placeholder="Экспериментальный OpenRouter"
                required
                value={form.name}
              />
            </label>
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-ink/70">Тип провайдера</span>
              <select
                className="ui-field"
                onChange={(event) => {
                  const provider_kind = event.target.value as ProviderKind;
                  setForm((current) => ({
                    ...current,
                    provider_kind,
                    base_url: current.base_url || DEFAULT_BASE_URLS[provider_kind] || "",
                    model: current.model === DEFAULT_MODELS[current.provider_kind] ? DEFAULT_MODELS[provider_kind] : current.model,
                  }));
                }}
                value={form.provider_kind}
              >
                {PROVIDER_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {getProviderKindLabel(option.value)} · {option.description}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-ink/70">Базовый URL</span>
              <input
                className="ui-field"
                onChange={(event) => setForm((current) => ({ ...current, base_url: event.target.value }))}
                placeholder={DEFAULT_BASE_URLS[form.provider_kind] ?? "https://example.local/v1"}
                value={form.base_url}
              />
            </label>
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-ink/70">Модель</span>
              <input
                className="ui-field"
                onChange={(event) => setForm((current) => ({ ...current, model: event.target.value }))}
                placeholder={DEFAULT_MODELS[form.provider_kind]}
                required
                value={form.model}
              />
            </label>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-ink/70">Температура</span>
              <input
                className="ui-field"
                max="2"
                min="0"
                onChange={(event) => setForm((current) => ({ ...current, temperature: event.target.value }))}
                step="0.1"
                type="number"
                value={form.temperature}
              />
            </label>
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-ink/70">Стоимость входа / 1k</span>
              <input
                className="ui-field"
                min="0"
                onChange={(event) => setForm((current) => ({ ...current, input_cost_per_1k_tokens: event.target.value }))}
                placeholder="0.000000"
                step="0.000001"
                type="number"
                value={form.input_cost_per_1k_tokens}
              />
            </label>
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-ink/70">Стоимость выхода / 1k</span>
              <input
                className="ui-field"
                min="0"
                onChange={(event) => setForm((current) => ({ ...current, output_cost_per_1k_tokens: event.target.value }))}
                placeholder="0.000000"
                step="0.000001"
                type="number"
                value={form.output_cost_per_1k_tokens}
              />
            </label>
          </div>

          <label className="block">
            <span className="mb-2 block text-sm font-semibold text-ink/70">
              Секрет {editingProviderId ? "(оставьте пустым, чтобы сохранить текущее значение)" : ""}
            </span>
            <input
              autoComplete="new-password"
              className="ui-field"
              onChange={(event) => setForm((current) => ({ ...current, secret: event.target.value }))}
              placeholder={form.provider_kind === "gigachat" ? "Ключ авторизации" : "API-ключ или токен"}
              type="password"
              value={form.secret}
            />
          </label>

          <label className="flex items-center gap-3 rounded-2xl border border-black/10 bg-white/60 px-4 py-3 text-sm text-ink">
            <input
              checked={form.enabled}
              onChange={(event) => setForm((current) => ({ ...current, enabled: event.target.checked }))}
              type="checkbox"
            />
            Включить этот профиль сразу после сохранения
          </label>

          <div className="flex flex-wrap gap-3">
            <button className="ui-button-primary" disabled={saving} type="submit">
              {saving ? "Сохраняем..." : editingProviderId ? "Обновить профиль" : "Создать профиль"}
            </button>
            <button className="ui-button-secondary" onClick={resetForm} type="button">
              Сбросить
            </button>
          </div>
        </form>

        <div className="glass-panel space-y-4 rounded-[28px] border border-black/10 p-6 shadow-panel">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-ember">Маршрутизация агентов</p>
            <h3 className="mt-2 text-2xl font-extrabold text-ink">Отдельные правила для агентов</h3>
            <p className="mt-3 text-sm leading-7 text-ink/70">
              Направляйте `qa` и `change-tracker` на другой профиль без смены
              глобального провайдера по умолчанию.
            </p>
          </div>

          {AGENT_OPTIONS.map((agent) => {
            const draft = overrideDrafts[agent.key];
            return (
              <article key={agent.key} className="rounded-[24px] border border-black/10 bg-white/70 p-4">
                <div className="flex flex-col gap-3">
                  <div>
                    <p className="text-sm font-bold text-ink">{agent.label}</p>
                    <p className="text-xs uppercase tracking-[0.14em] text-ink/45">{agent.key}</p>
                  </div>
                  <select
                    className="ui-field"
                    onChange={(event) =>
                      setOverrideDrafts((current) => ({
                        ...current,
                        [agent.key]: {
                          ...(current[agent.key] ?? { enabled: false }),
                          provider_config_id: event.target.value,
                        },
                      }))
                    }
                    value={draft?.provider_config_id ?? ""}
                  >
                    <option value="" disabled>
                      Выберите провайдера
                    </option>
                    {providers.map((provider) => (
                      <option key={provider.id} value={provider.id}>
                        {provider.name} · {getProviderKindLabel(provider.provider_kind)} · {provider.model}
                      </option>
                    ))}
                  </select>
                  <label className="flex items-center gap-3 text-sm text-ink">
                    <input
                      checked={draft?.enabled ?? false}
                      onChange={(event) =>
                        setOverrideDrafts((current) => ({
                          ...current,
                          [agent.key]: {
                            ...(current[agent.key] ?? { provider_config_id: providers[0]?.id ?? "" }),
                            enabled: event.target.checked,
                          },
                        }))
                      }
                      type="checkbox"
                    />
                    Правило активно
                  </label>
                  <button
                    className="ui-button-secondary"
                    disabled={savingOverrideKey === agent.key || !draft?.provider_config_id}
                    onClick={() => void handleSaveOverride(agent.key)}
                    type="button"
                  >
                    {savingOverrideKey === agent.key ? "Сохраняем..." : "Сохранить правило"}
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      </div>

      <div className="space-y-4">
        {providers.map((provider) => (
          <article key={provider.id} className="glass-panel rounded-[28px] border border-black/10 p-5 shadow-panel">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-ink px-3 py-1 text-xs font-bold uppercase tracking-[0.16em] text-white">
                    {getProviderKindLabel(provider.provider_kind)}
                  </span>
                  {provider.is_default ? (
                    <span className="rounded-full bg-pine/15 px-3 py-1 text-xs font-bold uppercase tracking-[0.16em] text-pine">
                      по умолчанию
                    </span>
                  ) : null}
                  {!provider.enabled ? (
                    <span className="rounded-full bg-ember/12 px-3 py-1 text-xs font-bold uppercase tracking-[0.16em] text-ember">
                      выключен
                    </span>
                  ) : null}
                </div>
                <div>
                  <h3 className="text-2xl font-extrabold text-ink">{provider.name}</h3>
                  <p className="mt-1 text-sm text-ink/60">{provider.base_url}</p>
                </div>
                <dl className="grid gap-3 text-sm text-ink/70 sm:grid-cols-2 xl:grid-cols-4">
                  <div>
                    <dt className="font-semibold text-ink/45">Модель</dt>
                    <dd>{provider.model}</dd>
                  </div>
                  <div>
                    <dt className="font-semibold text-ink/45">Температура</dt>
                    <dd>{provider.temperature}</dd>
                  </div>
                  <div>
                    <dt className="font-semibold text-ink/45">Секрет</dt>
                    <dd>{provider.masked_secret ?? "Не настроен"}</dd>
                  </div>
                  <div>
                    <dt className="font-semibold text-ink/45">Используется для</dt>
                    <dd>
                      {provider.used_by_agents.length > 0
                        ? provider.used_by_agents.map((agentKey) => getAgentKeyLabel(agentKey)).join(", ")
                        : "Только профиль по умолчанию"}
                    </dd>
                  </div>
                </dl>
                {testMessages[provider.id] ? (
                  <p className="rounded-2xl bg-black/5 px-4 py-3 text-sm text-ink/75">{testMessages[provider.id]}</p>
                ) : null}
              </div>

              <div className="flex flex-wrap gap-3">
                <button className="ui-button-secondary" onClick={() => startEdit(provider)} type="button">
                  Изменить
                </button>
                <button
                  className="ui-button-secondary"
                  disabled={testingProviderId === provider.id}
                  onClick={() => void handleTest(provider.id)}
                  type="button"
                >
                  {testingProviderId === provider.id ? "Проверяем..." : "Проверить подключение"}
                </button>
                <button
                  className="ui-button-primary"
                  disabled={settingDefaultId === provider.id || provider.is_default}
                  onClick={() => void handleSetDefault(provider.id)}
                  type="button"
                >
                  {provider.is_default
                    ? "Текущий профиль"
                    : settingDefaultId === provider.id
                      ? "Применяем..."
                      : "Сделать по умолчанию"}
                </button>
              </div>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
