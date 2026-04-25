import { useEffect, useMemo, useState } from "react";

import {
  adminApi,
  type AgentPromptConfigRead,
  type AgentPromptVersionRead,
} from "@/api/adminApi";
import { LoadingSpinner } from "@/shared/components/LoadingSpinner";
import { getApiErrorMessage } from "@/shared/lib/apiError";
import { formatDateTimeFull, getAgentKeyLabel } from "@/shared/lib/locale";

type PromptDraft = {
  description: string;
  enabled: boolean;
  system_prompt: string;
};

function toDraft(config: AgentPromptConfigRead): PromptDraft {
  return {
    description: config.override_description ?? config.default_description,
    enabled: config.override_enabled,
    system_prompt: config.override_system_prompt ?? config.default_system_prompt,
  };
}

function replaceConfig(
  configs: AgentPromptConfigRead[],
  updatedConfig: AgentPromptConfigRead,
) {
  return configs.map((config) =>
    config.prompt_key === updatedConfig.prompt_key ? updatedConfig : config,
  );
}

export default function AgentPromptsPage() {
  const [configs, setConfigs] = useState<AgentPromptConfigRead[]>([]);
  const [selectedPromptKey, setSelectedPromptKey] = useState<string | null>(null);
  const [versions, setVersions] = useState<AgentPromptVersionRead[]>([]);
  const [draft, setDraft] = useState<PromptDraft | null>(null);
  const [loading, setLoading] = useState(true);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [restoringVersionId, setRestoringVersionId] = useState<string | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);

  const selectedConfig = useMemo(
    () => configs.find((config) => config.prompt_key === selectedPromptKey),
    [configs, selectedPromptKey],
  );

  async function loadConfigs() {
    try {
      setLoading(true);
      setError(null);
      const loadedConfigs = await adminApi.listPromptConfigs();
      setConfigs(loadedConfigs);
      const nextSelectedKey = selectedPromptKey ?? loadedConfigs[0]?.prompt_key;
      setSelectedPromptKey(nextSelectedKey ?? null);
      const nextConfig = loadedConfigs.find(
        (config) => config.prompt_key === nextSelectedKey,
      );
      if (nextConfig) {
        setDraft(toDraft(nextConfig));
      }
    } catch (caught) {
      setError(
        getApiErrorMessage(caught, "Не удалось загрузить промпты агентов."),
      );
    } finally {
      setLoading(false);
    }
  }

  async function loadVersions(promptKey: string) {
    try {
      setVersionsLoading(true);
      setVersions(await adminApi.listPromptVersions(promptKey));
    } catch (caught) {
      setError(
        getApiErrorMessage(caught, "Не удалось загрузить историю промпта."),
      );
    } finally {
      setVersionsLoading(false);
    }
  }

  useEffect(() => {
    void loadConfigs();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!selectedConfig) {
      setVersions([]);
      setDraft(null);
      return;
    }

    setDraft(toDraft(selectedConfig));
    void loadVersions(selectedConfig.prompt_key);
  }, [selectedConfig?.prompt_key]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedConfig || !draft) {
      return;
    }

    try {
      setSaving(true);
      setError(null);
      const updatedConfig = await adminApi.updatePromptConfig(
        selectedConfig.prompt_key,
        draft,
      );
      setConfigs((current) => replaceConfig(current, updatedConfig));
      setDraft(toDraft(updatedConfig));
      await loadVersions(updatedConfig.prompt_key);
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось сохранить промпт."));
    } finally {
      setSaving(false);
    }
  }

  async function handleDisableOverride() {
    if (!selectedConfig || !draft) {
      return;
    }

    try {
      setSaving(true);
      setError(null);
      const updatedConfig = await adminApi.updatePromptConfig(
        selectedConfig.prompt_key,
        {
          ...draft,
          enabled: false,
        },
      );
      setConfigs((current) => replaceConfig(current, updatedConfig));
      setDraft(toDraft(updatedConfig));
      await loadVersions(updatedConfig.prompt_key);
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось отключить редакцию."));
    } finally {
      setSaving(false);
    }
  }

  async function handleRestore(versionId: string) {
    if (!selectedConfig) {
      return;
    }

    try {
      setRestoringVersionId(versionId);
      setError(null);
      const updatedConfig = await adminApi.restorePromptVersion(
        selectedConfig.prompt_key,
        versionId,
      );
      setConfigs((current) => replaceConfig(current, updatedConfig));
      setDraft(toDraft(updatedConfig));
      await loadVersions(updatedConfig.prompt_key);
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось восстановить версию."));
    } finally {
      setRestoringVersionId(null);
    }
  }

  if (loading) {
    return <LoadingSpinner label="Загрузка промптов агентов" />;
  }

  return (
    <section className="space-y-6">
      <header className="glass-panel rounded-[14px] border border-black/10 p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="section-eyebrow">LLM prompts</p>
            <h2 className="mt-2 text-2xl font-semibold text-[#172b4d]">
              Описания и системные промпты агентов
            </h2>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-[#44546f]">
              Редакции применяются к новым вызовам LangGraph. История изменений
              сохраняется для отката.
            </p>
          </div>
          <div className="rounded-[10px] border border-[rgba(9,30,66,0.12)] bg-[#fafbfc] px-4 py-3 text-sm text-[#44546f]">
            Активных редакций:{" "}
            <span className="font-semibold text-[#172b4d]">
              {configs.filter((config) => config.override_enabled).length}
            </span>
          </div>
        </div>
        {error ? (
          <p
            aria-live="polite"
            className="mt-4 rounded-[10px] bg-[#fdecec] px-4 py-3 text-sm text-[#ae2e24]"
          >
            {error}
          </p>
        ) : null}
      </header>

      <div className="grid gap-6 xl:grid-cols-[340px_minmax(0,1fr)]">
        <aside className="glass-panel rounded-[14px] border border-black/10 p-3">
          <div className="space-y-2">
            {configs.map((config) => (
              <button
                className={[
                  "w-full rounded-[10px] border px-4 py-3 text-left transition-[background-color,border-color]",
                  selectedPromptKey === config.prompt_key
                    ? "border-[#0c66e4] bg-[#e9f2ff]"
                    : "border-transparent bg-white hover:border-[rgba(9,30,66,0.12)] hover:bg-[#fafbfc]",
                ].join(" ")}
                key={config.prompt_key}
                onClick={() => setSelectedPromptKey(config.prompt_key)}
                type="button"
              >
                <span className="block text-sm font-semibold text-[#172b4d]">
                  {config.name}
                </span>
                <span className="mt-1 block text-xs text-[#626f86]">
                  {getAgentKeyLabel(config.agent_key)} / {config.prompt_key}
                </span>
                <span className="mt-2 block text-xs font-semibold uppercase tracking-[0.12em] text-[#626f86]">
                  {config.override_enabled ? "редакция активна" : "по умолчанию"}
                </span>
              </button>
            ))}
          </div>
        </aside>

        {selectedConfig && draft ? (
          <div className="space-y-6">
            <form
              className="glass-panel rounded-[14px] border border-black/10 p-6"
              onSubmit={handleSubmit}
            >
              <div className="flex flex-col gap-4 border-b border-[rgba(9,30,66,0.12)] pb-5 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#626f86]">
                    {selectedConfig.prompt_key}
                  </p>
                  <h3 className="mt-2 text-xl font-semibold text-[#172b4d]">
                    {selectedConfig.name}
                  </h3>
                  <p className="mt-2 text-sm text-[#44546f]">
                    Агент: {getAgentKeyLabel(selectedConfig.agent_key)}
                  </p>
                </div>
                <label className="flex items-center gap-3 rounded-[10px] border border-[rgba(9,30,66,0.12)] bg-[#fafbfc] px-4 py-3 text-sm text-[#172b4d]">
                  <input
                    checked={draft.enabled}
                    onChange={(event) =>
                      setDraft((current) =>
                        current
                          ? { ...current, enabled: event.target.checked }
                          : current,
                      )
                    }
                    type="checkbox"
                  />
                  Использовать редакцию
                </label>
              </div>

              <div className="mt-5 space-y-5">
                <label className="block">
                  <span className="mb-2 block text-sm font-semibold text-[#44546f]">
                    Описание агента
                  </span>
                  <textarea
                    className="ui-field min-h-28 resize-y"
                    onChange={(event) =>
                      setDraft((current) =>
                        current
                          ? { ...current, description: event.target.value }
                          : current,
                      )
                    }
                    required
                    value={draft.description}
                  />
                </label>

                <label className="block">
                  <span className="mb-2 block text-sm font-semibold text-[#44546f]">
                    Системный промпт
                  </span>
                  <textarea
                    className="ui-field min-h-[360px] resize-y font-mono leading-6"
                    onChange={(event) =>
                      setDraft((current) =>
                        current
                          ? { ...current, system_prompt: event.target.value }
                          : current,
                      )
                    }
                    required
                    value={draft.system_prompt}
                  />
                </label>
              </div>

              <div className="mt-5 flex flex-wrap gap-3">
                <button className="ui-button-primary" disabled={saving} type="submit">
                  {saving ? "Сохраняем..." : "Сохранить редакцию"}
                </button>
                <button
                  className="ui-button-secondary"
                  onClick={() =>
                    setDraft({
                      description: selectedConfig.default_description,
                      enabled: true,
                      system_prompt: selectedConfig.default_system_prompt,
                    })
                  }
                  type="button"
                >
                  Вставить значения по умолчанию
                </button>
                <button
                  className="ui-button-secondary"
                  disabled={saving || !selectedConfig.revision}
                  onClick={() => void handleDisableOverride()}
                  type="button"
                >
                  Отключить редакцию
                </button>
              </div>
            </form>

            <section className="glass-panel rounded-[14px] border border-black/10 p-6">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h3 className="text-lg font-semibold text-[#172b4d]">
                    История редакций
                  </h3>
                  <p className="mt-1 text-sm text-[#626f86]">
                    Текущая версия: {selectedConfig.revision ?? "нет редакций"}.
                  </p>
                </div>
                <button
                  className="ui-button-secondary"
                  disabled={versionsLoading}
                  onClick={() => void loadVersions(selectedConfig.prompt_key)}
                  type="button"
                >
                  Обновить историю
                </button>
              </div>

              <div className="mt-5 space-y-3">
                {versionsLoading ? (
                  <p className="rounded-[10px] border border-dashed border-[rgba(9,30,66,0.16)] px-4 py-5 text-sm text-[#626f86]">
                    Загружаем историю...
                  </p>
                ) : versions.length === 0 ? (
                  <p className="rounded-[10px] border border-dashed border-[rgba(9,30,66,0.16)] px-4 py-5 text-sm text-[#626f86]">
                    Для этого промпта пока нет сохранённых редакций.
                  </p>
                ) : (
                  versions.map((version) => (
                    <article
                      className="rounded-[10px] border border-[rgba(9,30,66,0.12)] bg-white p-4"
                      key={version.id}
                    >
                      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                        <div>
                          <h4 className="text-sm font-semibold text-[#172b4d]">
                            Версия {version.revision}
                          </h4>
                          <p className="mt-1 text-sm text-[#626f86]">
                            {formatDateTimeFull(version.created_at)} /{" "}
                            {version.enabled ? "активная редакция" : "отключена"}
                          </p>
                          <p className="mt-3 line-clamp-2 text-sm leading-6 text-[#44546f]">
                            {version.description}
                          </p>
                        </div>
                        <button
                          className="ui-button-secondary"
                          disabled={restoringVersionId === version.id}
                          onClick={() => void handleRestore(version.id)}
                          type="button"
                        >
                          {restoringVersionId === version.id
                            ? "Возвращаем..."
                            : "Вернуть версию"}
                        </button>
                      </div>
                    </article>
                  ))
                )}
              </div>
            </section>
          </div>
        ) : (
          <section className="glass-panel rounded-[14px] border border-black/10 p-6">
            <p className="text-sm text-[#626f86]">
              Зарегистрированные промпты агентов не найдены.
            </p>
          </section>
        )}
      </div>
    </section>
  );
}
