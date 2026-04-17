import { useEffect, useEffectEvent, useState } from "react";
import { useParams } from "react-router-dom";

import { projectsApi, type CustomRuleCreate, type CustomRuleRead, type ProjectRead } from "@/api/projectsApi";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { LoadingSpinner } from "@/shared/components/LoadingSpinner";
import { getApiErrorMessage } from "@/shared/lib/apiError";

const EMPTY_RULE: CustomRuleCreate = {
  title: "",
  description: "",
  applies_to_tags: [],
  is_active: true,
};

export default function CustomRulesEditor() {
  const { projectId } = useParams();
  const [project, setProject] = useState<ProjectRead | null>(null);
  const [rules, setRules] = useState<CustomRuleRead[]>([]);
  const [form, setForm] = useState<CustomRuleCreate>(EMPTY_RULE);
  const [editingRuleId, setEditingRuleId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deletingRuleId, setDeletingRuleId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rulePendingDeletion, setRulePendingDeletion] = useState<CustomRuleRead | null>(null);

  async function loadData() {
    if (!projectId) {
      setError("Не найден идентификатор проекта.");
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const [loadedProject, loadedRules] = await Promise.all([
        projectsApi.get(projectId),
        projectsApi.listRules(projectId),
      ]);
      setProject(loadedProject);
      setRules(loadedRules);
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось загрузить пользовательские правила."));
    } finally {
      setLoading(false);
    }
  }

  const onLoadData = useEffectEvent(loadData);

  // Effect Events must stay out of deps, otherwise the load effect re-triggers itself.
  useEffect(() => {
    void onLoadData();
  }, [projectId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!projectId) {
      return;
    }

    try {
      setSaving(true);
      const payload = {
        ...form,
        applies_to_tags: form.applies_to_tags.filter(Boolean),
      };

      if (editingRuleId) {
        const updated = await projectsApi.updateRule(projectId, editingRuleId, payload);
        setRules((current) => current.map((rule) => (rule.id === editingRuleId ? updated : rule)));
      } else {
        const created = await projectsApi.createRule(projectId, payload);
        setRules((current) => [created, ...current]);
      }

      setEditingRuleId(null);
      setForm(EMPTY_RULE);
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось сохранить правило."));
    } finally {
      setSaving(false);
    }
  }

  function startEdit(rule: CustomRuleRead) {
    setEditingRuleId(rule.id);
    setForm({
      title: rule.title,
      description: rule.description,
      applies_to_tags: rule.applies_to_tags,
      is_active: rule.is_active,
    });
  }

  function requestDelete(ruleId: string) {
    const rule = rules.find((item) => item.id === ruleId);
    if (!rule) {
      return;
    }
    setRulePendingDeletion(rule);
  }

  async function handleDelete() {
    if (!projectId || !rulePendingDeletion) {
      return;
    }

    try {
      setDeletingRuleId(rulePendingDeletion.id);
      await projectsApi.removeRule(projectId, rulePendingDeletion.id);
      setRules((current) => current.filter((rule) => rule.id !== rulePendingDeletion.id));
      setRulePendingDeletion(null);
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось удалить правило."));
    } finally {
      setDeletingRuleId(null);
    }
  }

  if (loading) {
    return <LoadingSpinner label="Загрузка правил" />;
  }

  return (
    <section className="space-y-6">
      <header className="glass-panel rounded-[32px] border border-black/10 p-8 shadow-panel">
        <p className="text-xs font-bold uppercase tracking-[0.2em] text-ember">Пользовательские правила</p>
        <h2 className="mt-3 text-3xl font-extrabold text-ink sm:text-4xl">{project?.name ?? "Правила проекта"}</h2>
        <p className="mt-4 text-sm leading-7 text-ink/70">
          Правила применяются во время проверки, если совпадают теги или если у
          правила нет фильтра по тегам.
        </p>
        {error ? (
          <p aria-live="polite" className="mt-4 rounded-2xl bg-ember/10 px-4 py-3 text-sm text-ember">
            {error}
          </p>
        ) : null}
      </header>

      <form className="glass-panel space-y-4 rounded-[28px] border border-black/10 p-6 shadow-panel" onSubmit={handleSubmit}>
        <h3 className="text-xl font-bold text-ink">{editingRuleId ? "Редактирование правила" : "Новое правило"}</h3>
        <label className="block">
          <span className="mb-2 block text-sm font-semibold text-ink/70">Название правила</span>
          <input
            autoComplete="off"
            className="ui-field"
            name="rule-title"
            onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
            placeholder="Правило по авторизации"
            required
            value={form.title}
          />
        </label>
        <label className="block">
          <span className="mb-2 block text-sm font-semibold text-ink/70">Описание</span>
          <textarea
            className="ui-field min-h-32"
            name="rule-description"
            onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
            placeholder="Опишите, что именно должно проверяться..."
            required
            value={form.description}
          />
        </label>
        <label className="block">
          <span className="mb-2 block text-sm font-semibold text-ink/70">Теги</span>
          <input
            autoComplete="off"
            className="ui-field"
            name="rule-tags"
            onChange={(event) =>
              setForm((current) => ({
                ...current,
                applies_to_tags: event.target.value
                  .split(",")
                  .map((tag) => tag.trim())
                  .filter(Boolean),
              }))
            }
            placeholder="авторизация, api"
            value={form.applies_to_tags.join(", ")}
          />
        </label>
        <label className="flex items-center gap-3 text-sm text-ink">
          <input
            checked={form.is_active}
            onChange={(event) => setForm((current) => ({ ...current, is_active: event.target.checked }))}
            type="checkbox"
          />
          Правило активно
        </label>
        <div className="flex flex-wrap gap-3">
          <button
            className="ui-button-primary"
            disabled={saving}
            type="submit"
          >
            {saving ? "Сохраняем..." : editingRuleId ? "Обновить правило" : "Создать правило"}
          </button>
          {editingRuleId ? (
            <button
              className="ui-button-secondary"
              onClick={() => {
                setEditingRuleId(null);
                setForm(EMPTY_RULE);
              }}
              type="button"
            >
              Отмена
            </button>
          ) : null}
        </div>
      </form>

      <div className="space-y-4">
        {rules.map((rule) => (
          <article key={rule.id} className="glass-panel rounded-[28px] border border-black/10 p-5 shadow-panel">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.16em] text-ember">
                  {rule.is_active ? "активно" : "выключено"}
                </p>
                <h3 className="mt-2 text-xl font-bold text-ink">{rule.title}</h3>
                <p className="mt-3 text-sm leading-7 text-ink/70">{rule.description}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {rule.applies_to_tags.length === 0 ? (
                    <span className="rounded-full bg-pine/10 px-3 py-1 text-xs font-semibold text-pine">все теги</span>
                  ) : (
                    rule.applies_to_tags.map((tag) => (
                      <span key={tag} className="rounded-full bg-ink/6 px-3 py-1 text-xs font-semibold text-ink/75">
                        {tag}
                      </span>
                    ))
                  )}
                </div>
              </div>

              <div className="flex flex-wrap gap-3">
                <button
                  className="ui-button-secondary"
                  onClick={() => startEdit(rule)}
                  type="button"
                >
                  Изменить
                </button>
                <button
                  className="ui-button-danger"
                  onClick={() => requestDelete(rule.id)}
                  type="button"
                >
                  Удалить
                </button>
              </div>
            </div>
          </article>
        ))}
      </div>

      <ConfirmDialog
        busy={deletingRuleId === rulePendingDeletion?.id}
        confirmLabel="Удалить правило"
        description={
          rulePendingDeletion
            ? `Удалить правило «${rulePendingDeletion.title}»? После этого оно перестанет применяться при проверке.`
            : ""
        }
        destructive
        onClose={() => setRulePendingDeletion(null)}
        onConfirm={handleDelete}
        open={rulePendingDeletion !== null}
        title="Удаление правила"
      />
    </section>
  );
}
