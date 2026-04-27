import { useEffect, useEffectEvent, useState } from "react";

import {
  adminApi,
  type AgentDirectoryRead,
  type AgentOverrideRead,
  type ProviderConfigPayload,
  type ProviderConfigRead,
  type ProviderKind,
  type VisionDetail,
  type VisionMessageOrder,
  type VisionSystemPromptMode,
} from "@/api/adminApi";
import { LoadingSpinner } from "@/shared/components/LoadingSpinner";
import { getApiErrorMessage } from "@/shared/lib/apiError";
import { getAgentKeyLabel, getProviderKindLabel } from "@/shared/lib/locale";

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
  vision_detail: VisionDetail;
  vision_enabled: boolean;
  vision_message_order: VisionMessageOrder;
  vision_system_prompt_mode: VisionSystemPromptMode;
};

type OverrideDraft = {
  enabled: boolean;
  provider_config_id: string;
};

const PROVIDER_OPTIONS: Array<{ description: string; value: ProviderKind }> = [
  { value: "openai", description: "Облачный профиль OpenAI" },
  { value: "ollama", description: "Локальный профиль Ollama" },
  { value: "openrouter", description: "Профиль OpenRouter" },
  { value: "gigachat", description: "Профиль GigaChat" },
  {
    value: "openai_compatible",
    description: "Совместимый сервер по OpenAI API",
  },
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

const VISION_SYSTEM_PROMPT_OPTIONS: Array<{
  description: string;
  value: VisionSystemPromptMode;
}> = [
  {
    value: "system_role",
    description: "Отправлять системную инструкцию отдельным system/developer сообщением",
  },
  {
    value: "inline_user",
    description: "Встраивать системную инструкцию в первый текстовый фрагмент user-сообщения",
  },
];

const VISION_MESSAGE_ORDER_OPTIONS: Array<{
  description: string;
  value: VisionMessageOrder;
}> = [
  {
    value: "text_first",
    description: "Сначала текстовая инструкция, затем изображение",
  },
  {
    value: "image_first",
    description: "Сначала изображение, затем текстовая инструкция",
  },
];

const VISION_DETAIL_OPTIONS: Array<{ description: string; value: VisionDetail }> = [
  { value: "default", description: "Не передавать detail, оставить поведение провайдера по умолчанию" },
  { value: "auto", description: "Провайдер сам выбирает уровень детализации" },
  { value: "low", description: "Быстрый и дешёвый режим для простых изображений" },
  { value: "high", description: "Максимально подробный режим для OCR и сложных схем" },
];

const EMPTY_FORM: ProviderFormState = {
  name: "",
  provider_kind: "openai",
  base_url: "",
  model: "",
  temperature: "0.2",
  enabled: false,
  input_cost_per_1k_tokens: "",
  output_cost_per_1k_tokens: "",
  secret: "",
  vision_enabled: true,
  vision_system_prompt_mode: "system_role",
  vision_message_order: "text_first",
  vision_detail: "default",
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
    vision_enabled: form.vision_enabled,
    vision_system_prompt_mode: form.vision_system_prompt_mode,
    vision_message_order: form.vision_message_order,
    vision_detail: form.vision_detail,
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
    input_cost_per_1k_tokens: provider.input_cost_per_1k_tokens
      ? String(provider.input_cost_per_1k_tokens)
      : "",
    output_cost_per_1k_tokens: provider.output_cost_per_1k_tokens
      ? String(provider.output_cost_per_1k_tokens)
      : "",
    secret: "",
    vision_enabled: provider.vision_enabled,
    vision_system_prompt_mode: provider.vision_system_prompt_mode,
    vision_message_order: provider.vision_message_order,
    vision_detail: provider.vision_detail,
  };
}

function buildOverrideDrafts(
  providers: ProviderConfigRead[],
  overrides: AgentOverrideRead[],
  agentOptions: AgentDirectoryRead[],
): Record<string, OverrideDraft> {
  const overrideByAgent = new Map(
    overrides.map((item) => [item.agent_key, item]),
  );
  const fallbackProviderId = providers[0]?.id ?? "";
  return Object.fromEntries(
    agentOptions.map((item) => {
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
  const [availableAgents, setAvailableAgents] = useState<AgentDirectoryRead[]>(
    [],
  );
  const [overrideDrafts, setOverrideDrafts] = useState<
    Record<string, OverrideDraft>
  >({});
  const [form, setForm] = useState<ProviderFormState>(EMPTY_FORM);
  const [editingProviderId, setEditingProviderId] = useState<string | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testingProviderId, setTestingProviderId] = useState<string | null>(
    null,
  );
  const [settingDefaultId, setSettingDefaultId] = useState<string | null>(null);
  const [savingOverrideKey, setSavingOverrideKey] = useState<string | null>(
    null,
  );
  const [testMessages, setTestMessages] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  async function loadData() {
    try {
      setLoading(true);
      setError(null);
      const [loadedProviders, loadedOverrides, loadedAgents] = await Promise.all([
        adminApi.listProviders(),
        adminApi.listOverrides(),
        adminApi.listAvailableAgents(),
      ]);
      setProviders(loadedProviders);
      setAvailableAgents(loadedAgents);
      setOverrideDrafts(
        buildOverrideDrafts(loadedProviders, loadedOverrides, loadedAgents),
      );
    } catch (caught) {
      setError(
        getApiErrorMessage(
          caught,
          "Не удалось загрузить настройки модельных профилей.",
        ),
      );
    } finally {
      setLoading(false);
    }
  }

  const onLoadData = useEffectEvent(loadData);

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
      setError(
        getApiErrorMessage(caught, "Не удалось сохранить модельный профиль."),
      );
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
        [providerId]: `${result.ok ? "Успешно" : "Ошибка"}${result.latency_ms ? ` / ${result.latency_ms} мс` : ""} / ${result.message}`,
      }));
    } catch (caught) {
      setError(
        getApiErrorMessage(caught, "Не удалось проверить модельный профиль."),
      );
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
      setError(
        getApiErrorMessage(caught, "Не удалось обновить профиль по умолчанию."),
      );
    } finally {
      setSettingDefaultId(null);
    }
  }

  async function handleSaveOverride(agentKey: string) {
    const draft = overrideDrafts[agentKey];
    if (!draft?.provider_config_id) {
      setError("Выберите профиль перед сохранением правила маршрутизации.");
      return;
    }

    try {
      setSavingOverrideKey(agentKey);
      await adminApi.updateOverride(
        agentKey,
        draft.provider_config_id,
        draft.enabled,
      );
      await loadData();
    } catch (caught) {
      setError(
        getApiErrorMessage(
          caught,
          "Не удалось сохранить правило маршрутизации.",
        ),
      );
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

  const agentNameByKey = new Map(
    availableAgents.map((agent) => [agent.key, agent.name]),
  );

  function getResolvedAgentLabel(agentKey: string) {
    return agentNameByKey.get(agentKey) ?? getAgentKeyLabel(agentKey);
  }

  if (loading) {
    return <LoadingSpinner label="Загрузка модельных профилей" />;
  }

  return (
    <section className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <form
          className="glass-panel space-y-4 rounded-[28px] border border-black/10 p-6 shadow-panel"
          onSubmit={handleSubmit}
        >
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.16em] text-ember">
                Модельный профиль
              </p>
              <h3 className="mt-2 text-2xl font-extrabold text-ink">
                {editingProviderId
                  ? "Редактирование рабочего профиля"
                  : "Создание нового профиля"}
              </h3>
            </div>
            {editingProviderId ? (
              <button
                className="ui-button-secondary"
                onClick={resetForm}
                type="button"
              >
                Отмена
              </button>
            ) : null}
          </div>

          {error ? (
            <p
              aria-live="polite"
              className="rounded-2xl bg-ember/10 px-4 py-3 text-sm text-ember"
            >
              {error}
            </p>
          ) : null}

          <div className="grid gap-4 md:grid-cols-2">
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-ink/70">
                Название профиля
              </span>
              <input
                className="ui-field"
                onChange={(event) =>
                  setForm((current) => ({ ...current, name: event.target.value }))
                }
                placeholder="Основной OpenRouter"
                required
                value={form.name}
              />
            </label>
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-ink/70">
                Тип подключения
              </span>
              <select
                className="ui-field"
                onChange={(event) => {
                  const provider_kind = event.target.value as ProviderKind;
                  setForm((current) => ({
                    ...current,
                    provider_kind,
                    base_url:
                      current.base_url ||
                      DEFAULT_BASE_URLS[provider_kind] ||
                      "",
                    model:
                      !current.model ||
                      current.model === DEFAULT_MODELS[current.provider_kind]
                        ? DEFAULT_MODELS[provider_kind]
                        : current.model,
                  }));
                }}
                value={form.provider_kind}
              >
                {PROVIDER_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {getProviderKindLabel(option.value)} / {option.description}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-ink/70">
                Базовый URL
              </span>
              <input
                className="ui-field"
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    base_url: event.target.value,
                  }))
                }
                placeholder={
                  DEFAULT_BASE_URLS[form.provider_kind] ??
                  "https://example.local/v1"
                }
                value={form.base_url}
              />
            </label>
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-ink/70">
                Модель
              </span>
              <input
                className="ui-field"
                onChange={(event) =>
                  setForm((current) => ({ ...current, model: event.target.value }))
                }
                placeholder={DEFAULT_MODELS[form.provider_kind]}
                required
                value={form.model}
              />
            </label>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-ink/70">
                Температура
              </span>
              <input
                className="ui-field"
                max="2"
                min="0"
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    temperature: event.target.value,
                  }))
                }
                step="0.1"
                type="number"
                value={form.temperature}
              />
            </label>
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-ink/70">
                Стоимость входа / 1k
              </span>
              <input
                className="ui-field"
                min="0"
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    input_cost_per_1k_tokens: event.target.value,
                  }))
                }
                placeholder="0.000000"
                step="0.000001"
                type="number"
                value={form.input_cost_per_1k_tokens}
              />
            </label>
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-ink/70">
                Стоимость выхода / 1k
              </span>
              <input
                className="ui-field"
                min="0"
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    output_cost_per_1k_tokens: event.target.value,
                  }))
                }
                placeholder="0.000000"
                step="0.000001"
                type="number"
                value={form.output_cost_per_1k_tokens}
              />
            </label>
          </div>

          <label className="block">
            <span className="mb-2 block text-sm font-semibold text-ink/70">
              Ключ доступа{" "}
              {editingProviderId
                ? "(оставьте пустым, чтобы сохранить текущее значение)"
                : ""}
            </span>
            <input
              autoComplete="new-password"
              className="ui-field"
              onChange={(event) =>
                setForm((current) => ({ ...current, secret: event.target.value }))
              }
              placeholder={
                form.provider_kind === "gigachat"
                  ? "Токен авторизации"
                  : "API-ключ или токен"
              }
              type="password"
              value={form.secret}
            />
          </label>

          <label className="flex items-center gap-3 rounded-2xl border border-black/10 bg-white/60 px-4 py-3 text-sm text-ink">
            <input
              checked={form.enabled}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  enabled: event.target.checked,
                }))
              }
              type="checkbox"
            />
            Включить этот профиль сразу после сохранения
          </label>

          <div className="rounded-[24px] border border-black/10 bg-white/60 p-5">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.16em] text-ember">
                Vision
              </p>
              <h4 className="mt-2 text-xl font-extrabold text-ink">
                Расширенные настройки multimodal-вызовов
              </h4>
              <p className="mt-2 text-sm leading-7 text-ink/65">
                Эти параметры используются для OCR, alt-text и остальных вызовов
                с изображениями. Здесь можно адаптировать профиль под требования
                конкретной vision-модели без правок runtime.
              </p>
            </div>

            <div className="mt-4 space-y-4">
              <label className="flex items-center gap-3 rounded-2xl border border-black/10 bg-[#f8fafc] px-4 py-3 text-sm text-ink">
                <input
                  checked={form.vision_enabled}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      vision_enabled: event.target.checked,
                    }))
                  }
                  type="checkbox"
                />
                Разрешить использовать профиль для vision- и OCR-сценариев
              </label>

              <div className="grid gap-4 md:grid-cols-3">
                <label className="block">
                  <span className="mb-2 block text-sm font-semibold text-ink/70">
                    Системная инструкция
                  </span>
                  <select
                    className="ui-field"
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        vision_system_prompt_mode:
                          event.target.value as VisionSystemPromptMode,
                      }))
                    }
                    value={form.vision_system_prompt_mode}
                  >
                    {VISION_SYSTEM_PROMPT_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.value}
                      </option>
                    ))}
                  </select>
                  <span className="mt-2 block text-xs leading-5 text-ink/55">
                    {
                      VISION_SYSTEM_PROMPT_OPTIONS.find(
                        (option) => option.value === form.vision_system_prompt_mode,
                      )?.description
                    }
                  </span>
                </label>

                <label className="block">
                  <span className="mb-2 block text-sm font-semibold text-ink/70">
                    Порядок частей
                  </span>
                  <select
                    className="ui-field"
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        vision_message_order:
                          event.target.value as VisionMessageOrder,
                      }))
                    }
                    value={form.vision_message_order}
                  >
                    {VISION_MESSAGE_ORDER_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.value}
                      </option>
                    ))}
                  </select>
                  <span className="mt-2 block text-xs leading-5 text-ink/55">
                    {
                      VISION_MESSAGE_ORDER_OPTIONS.find(
                        (option) => option.value === form.vision_message_order,
                      )?.description
                    }
                  </span>
                </label>

                <label className="block">
                  <span className="mb-2 block text-sm font-semibold text-ink/70">
                    Detail
                  </span>
                  <select
                    className="ui-field"
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        vision_detail: event.target.value as VisionDetail,
                      }))
                    }
                    value={form.vision_detail}
                  >
                    {VISION_DETAIL_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.value}
                      </option>
                    ))}
                  </select>
                  <span className="mt-2 block text-xs leading-5 text-ink/55">
                    {
                      VISION_DETAIL_OPTIONS.find(
                        (option) => option.value === form.vision_detail,
                      )?.description
                    }
                  </span>
                </label>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap gap-3">
            <button className="ui-button-primary" disabled={saving} type="submit">
              {saving
                ? "Сохраняем..."
                : editingProviderId
                  ? "Обновить профиль"
                  : "Создать профиль"}
            </button>
            <button
              className="ui-button-secondary"
              onClick={resetForm}
              type="button"
            >
              Сбросить
            </button>
          </div>
        </form>

        <div className="glass-panel space-y-4 rounded-[28px] border border-black/10 p-6 shadow-panel">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-ember">
              Маршрутизация
            </p>
            <h3 className="mt-2 text-2xl font-extrabold text-ink">
              Специальные правила для сценариев
            </h3>
            <p className="mt-3 text-sm leading-7 text-ink/70">
              Направляйте отдельные LLM-сценарии на выделенный профиль, не
              меняя глобальный профиль по умолчанию.
            </p>
          </div>

          {providers.length === 0 ? (
            <p className="rounded-2xl bg-black/5 px-4 py-3 text-sm text-ink/70">
              Сначала создайте хотя бы один профиль провайдера и назначьте его профилем по умолчанию. После этого здесь можно настраивать маршрутизацию отдельных агентов.
            </p>
          ) : null}

          {availableAgents.map((agent) => {
            const draft = overrideDrafts[agent.key];
            return (
              <article
                key={agent.key}
                className="rounded-[24px] border border-black/10 bg-white/70 p-4"
              >
                <div className="flex flex-col gap-3">
                  <div>
                    <p className="text-sm font-bold text-ink">{agent.name}</p>
                    <p className="text-xs uppercase tracking-[0.14em] text-ink/45">
                      {agent.key}
                    </p>
                    <p className="mt-2 text-sm leading-6 text-ink/65">
                      {agent.description}
                    </p>
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
                      Выберите профиль
                    </option>
                    {providers.map((provider) => (
                      <option key={provider.id} value={provider.id}>
                        {provider.name} /{" "}
                        {getProviderKindLabel(provider.provider_kind)} /{" "}
                        {provider.model}
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
                            ...(current[agent.key] ?? {
                              provider_config_id: providers[0]?.id ?? "",
                            }),
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
                    disabled={
                      savingOverrideKey === agent.key || !draft?.provider_config_id
                    }
                    onClick={() => void handleSaveOverride(agent.key)}
                    type="button"
                  >
                    {savingOverrideKey === agent.key
                      ? "Сохраняем..."
                      : "Сохранить правило"}
                  </button>
                </div>
              </article>
            );
          })}
          {availableAgents.length === 0 ? (
            <p className="rounded-2xl bg-black/5 px-4 py-3 text-sm text-ink/70">
              В системе пока не зарегистрировано отдельных LLM-сценариев для
              переопределения.
            </p>
          ) : null}
        </div>
      </div>

      <div className="space-y-4">
        {providers.length === 0 ? (
          <p className="glass-panel rounded-[28px] border border-black/10 px-5 py-4 text-sm text-ink/70 shadow-panel">
            В системе пока нет LLM-профилей. Агентные модели больше не подхватываются из `.env`: добавьте провайдер через админ-панель и назначьте его по умолчанию.
          </p>
        ) : null}
        {providers.map((provider) => (
          <article
            key={provider.id}
            className="glass-panel rounded-[28px] border border-black/10 p-5 shadow-panel"
          >
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
                  <h3 className="text-2xl font-extrabold text-ink">
                    {provider.name}
                  </h3>
                  <p className="mt-1 text-sm text-ink/60">
                    {provider.base_url}
                  </p>
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
                    <dt className="font-semibold text-ink/45">Ключ</dt>
                    <dd>{provider.masked_secret ?? "Не настроен"}</dd>
                  </div>
                  <div>
                    <dt className="font-semibold text-ink/45">
                      Используется для
                    </dt>
                    <dd>
                      {provider.used_by_agents.length > 0
                        ? provider.used_by_agents
                            .map((agentKey) => getResolvedAgentLabel(agentKey))
                            .join(", ")
                        : "Только профиль по умолчанию"}
                    </dd>
                  </div>
                </dl>
                <div className="rounded-[20px] border border-black/10 bg-white/60 px-4 py-4 text-sm text-ink/70">
                  <p className="font-semibold text-ink">Vision-профиль</p>
                  <p className="mt-2">
                    {provider.vision_enabled ? "Включен" : "Отключен"} / system:{" "}
                    {provider.vision_system_prompt_mode} / order:{" "}
                    {provider.vision_message_order} / detail:{" "}
                    {provider.vision_detail}
                  </p>
                </div>
                {testMessages[provider.id] ? (
                  <p className="rounded-2xl bg-black/5 px-4 py-3 text-sm text-ink/75">
                    {testMessages[provider.id]}
                  </p>
                ) : null}
              </div>

              <div className="flex flex-wrap gap-3">
                <button
                  className="ui-button-secondary"
                  onClick={() => startEdit(provider)}
                  type="button"
                >
                  Изменить
                </button>
                <button
                  className="ui-button-secondary"
                  disabled={testingProviderId === provider.id}
                  onClick={() => void handleTest(provider.id)}
                  type="button"
                >
                  {testingProviderId === provider.id
                    ? "Проверяем..."
                    : "Проверить подключение"}
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
