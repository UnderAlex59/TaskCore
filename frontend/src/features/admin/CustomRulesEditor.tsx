import { useEffect, useEffectEvent, useState } from "react";
import { useParams } from "react-router-dom";

import {
  projectsApi,
  type CustomRuleCreate,
  type CustomRuleRead,
  type ProjectRead,
  type ValidationNodeSettings,
} from "@/api/projectsApi";
import { taskTagsApi, type TaskTagOption } from "@/api/taskTagsApi";
import TagMultiSelect from "@/shared/components/TagMultiSelect";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { LoadingSpinner } from "@/shared/components/LoadingSpinner";
import { getApiErrorMessage } from "@/shared/lib/apiError";

const EMPTY_RULE: CustomRuleCreate = {
  title: "",
  description: "",
  applies_to_tags: [],
  is_active: true,
};

const VALIDATION_NODE_FIELDS: Array<{
  key: keyof ValidationNodeSettings;
  title: string;
  description: string;
}> = [
  {
    key: "core_rules",
    title: "Базовые правила",
    description:
      "Проверка минимальной полноты требования, длины описания и явных неоднозначностей.",
  },
  {
    key: "custom_rules",
    title: "Пользовательские правила",
    description: "Проектные проверки по кастомным правилам и тегам.",
  },
  {
    key: "context_questions",
    title: "Контекст и уточнения",
    description:
      "Поиск недостающего контекста, похожих задач и запросы на вложения.",
  },
];

export default function CustomRulesEditor() {
  const { projectId } = useParams();
  const [project, setProject] = useState<ProjectRead | null>(null);
  const [rules, setRules] = useState<CustomRuleRead[]>([]);
  const [taskTags, setTaskTags] = useState<TaskTagOption[]>([]);
  const [form, setForm] = useState<CustomRuleCreate>(EMPTY_RULE);
  const [editingRuleId, setEditingRuleId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savingSettings, setSavingSettings] = useState(false);
  const [deletingRuleId, setDeletingRuleId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rulePendingDeletion, setRulePendingDeletion] =
    useState<CustomRuleRead | null>(null);

  async function loadData() {
    if (!projectId) {
      setError("Не найден идентификатор проекта.");
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const [loadedProject, loadedRules, loadedTaskTags] = await Promise.all([
        projectsApi.get(projectId),
        projectsApi.listRules(projectId),
        taskTagsApi.list(),
      ]);
      setProject(loadedProject);
      setRules(loadedRules);
      setTaskTags(loadedTaskTags);
    } catch (caught) {
      setError(
        getApiErrorMessage(
          caught,
          "Не удалось загрузить пользовательские правила.",
        ),
      );
    } finally {
      setLoading(false);
    }
  }

  function updateValidationNodeSetting(
    key: keyof ValidationNodeSettings,
    value: boolean,
  ) {
    setProject((current) => {
      if (!current) {
        return current;
      }

      return {
        ...current,
        validation_node_settings: {
          ...current.validation_node_settings,
          [key]: value,
        },
      };
    });
  }

  async function handleSaveSettings() {
    if (!projectId || !project) {
      return;
    }

    try {
      setSavingSettings(true);
      setError(null);
      const updatedProject = await projectsApi.update(projectId, {
        validation_node_settings: project.validation_node_settings,
      });
      setProject(updatedProject);
    } catch (caught) {
      setError(
        getApiErrorMessage(
          caught,
          "Не удалось сохранить настройки узлов валидации.",
        ),
      );
    } finally {
      setSavingSettings(false);
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
        const updated = await projectsApi.updateRule(
          projectId,
          editingRuleId,
          payload,
        );
        setRules((current) =>
          current.map((rule) => (rule.id === editingRuleId ? updated : rule)),
        );
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
      setRules((current) =>
        current.filter((rule) => rule.id !== rulePendingDeletion.id),
      );
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
        <p className="text-xs font-bold uppercase tracking-[0.2em] text-ember">
          Пользовательские правила
        </p>
        <h2 className="mt-3 text-3xl font-extrabold text-ink sm:text-4xl">
          {project?.name ?? "Правила проекта"}
        </h2>
        <p className="mt-4 text-sm leading-7 text-ink/70">
          Правила применяются во время проверки, если совпадают теги или если у
          правила нет фильтра по тегам.
        </p>
        {error ? (
          <p
            aria-live="polite"
            className="mt-4 rounded-2xl bg-ember/10 px-4 py-3 text-sm text-ember"
          >
            {error}
          </p>
        ) : null}
      </header>

      {project ? (
        <section className="glass-panel space-y-5 rounded-[28px] border border-black/10 p-6 shadow-panel">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-ember">
              Узлы LangGraph
            </p>
            <h3 className="mt-2 text-xl font-bold text-ink">
              Конфигурация проверки задач
            </h3>
            <p className="mt-3 text-sm leading-7 text-ink/70">
              Администратор может отключать отдельные узлы графа валидации для
              этого проекта. Отключённые узлы не участвуют в запуске проверки.
            </p>
          </div>

          <div className="space-y-3">
            {VALIDATION_NODE_FIELDS.map((item) => (
              <label
                key={item.key}
                className="flex items-start justify-between gap-4 rounded-[18px] border border-black/10 bg-white/80 p-4"
              >
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-ink">{item.title}</p>
                  <p className="mt-1 text-sm leading-6 text-ink/70">
                    {item.description}
                  </p>
                </div>
                <input
                  checked={project.validation_node_settings[item.key]}
                  onChange={(event) =>
                    updateValidationNodeSetting(item.key, event.target.checked)
                  }
                  type="checkbox"
                />
              </label>
            ))}
          </div>

          <div className="flex flex-wrap gap-3">
            <button
              className="ui-button-primary"
              disabled={savingSettings}
              onClick={() => void handleSaveSettings()}
              type="button"
            >
              {savingSettings ? "Сохраняем..." : "Сохранить конфигурацию"}
            </button>
          </div>
        </section>
      ) : null}

      <form
        className="glass-panel space-y-4 rounded-[28px] border border-black/10 p-6 shadow-panel"
        onSubmit={handleSubmit}
      >
        <h3 className="text-xl font-bold text-ink">
          {editingRuleId ? "Редактирование правила" : "Новое правило"}
        </h3>
        <label className="block">
          <span className="mb-2 block text-sm font-semibold text-ink/70">
            Название правила
          </span>
          <input
            autoComplete="off"
            className="ui-field"
            name="rule-title"
            onChange={(event) =>
              setForm((current) => ({ ...current, title: event.target.value }))
            }
            placeholder="Правило по авторизации"
            required
            value={form.title}
          />
        </label>
        <label className="block">
          <span className="mb-2 block text-sm font-semibold text-ink/70">
            Описание
          </span>
          <textarea
            className="ui-field min-h-32"
            name="rule-description"
            onChange={(event) =>
              setForm((current) => ({
                ...current,
                description: event.target.value,
              }))
            }
            placeholder="Опишите, что именно должно проверяться..."
            required
            value={form.description}
          />
        </label>
        <label className="block">
          <span className="mb-2 block text-sm font-semibold text-ink/70">
            Теги
          </span>
          <TagMultiSelect
            helperText={
              taskTags.length === 0
                ? "Справочник тегов пока пуст. Оставьте поле пустым, чтобы правило применялось ко всем задачам."
                : "Если теги не выбраны, правило действует для всех задач проекта."
            }
            hideLabel
            label="Теги"
            name="rule-tags"
            noOptionsLabel="Справочник тегов пока пуст"
            onChange={(appliesToTags) =>
              setForm((current) => ({
                ...current,
                applies_to_tags: appliesToTags,
              }))
            }
            options={taskTags}
            placeholder="Выберите теги"
            searchPlaceholder="Найти тег"
            value={form.applies_to_tags}
          />
        </label>
        <label className="flex items-center gap-3 text-sm text-ink">
          <input
            checked={form.is_active}
            onChange={(event) =>
              setForm((current) => ({
                ...current,
                is_active: event.target.checked,
              }))
            }
            type="checkbox"
          />
          Правило активно
        </label>
        <div className="flex flex-wrap gap-3">
          <button className="ui-button-primary" disabled={saving} type="submit">
            {saving
              ? "Сохраняем..."
              : editingRuleId
                ? "Обновить правило"
                : "Создать правило"}
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
          <article
            key={rule.id}
            className="glass-panel rounded-[28px] border border-black/10 p-5 shadow-panel"
          >
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.16em] text-ember">
                  {rule.is_active ? "активно" : "выключено"}
                </p>
                <h3 className="mt-2 text-xl font-bold text-ink">
                  {rule.title}
                </h3>
                <p className="mt-3 text-sm leading-7 text-ink/70">
                  {rule.description}
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {rule.applies_to_tags.length === 0 ? (
                    <span className="rounded-full bg-pine/10 px-3 py-1 text-xs font-semibold text-pine">
                      все теги
                    </span>
                  ) : (
                    rule.applies_to_tags.map((tag) => (
                      <span
                        key={tag}
                        className="rounded-full bg-ink/6 px-3 py-1 text-xs font-semibold text-ink/75"
                      >
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
