import { useState } from "react";

import type { ProjectCreate } from "@/api/projectsApi";

interface Props {
  canCreate: boolean;
  loading?: boolean;
  onCreate: (payload: ProjectCreate) => Promise<void>;
}

export default function CreateProjectModal({
  onCreate,
  canCreate,
  loading = false,
}: Props) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const formId = "create-project-form";

  if (!canCreate) {
    return null;
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onCreate({ name, description: description.trim() || null });
    setName("");
    setDescription("");
    setOpen(false);
  }

  return (
    <div className="flex flex-col items-start gap-3">
      <button
        aria-controls={formId}
        aria-expanded={open}
        className="ui-button-secondary"
        onClick={() => setOpen((current) => !current)}
        type="button"
      >
        {open ? "Скрыть форму" : "Создать проект"}
      </button>

      {open ? (
        <form
          className="glass-panel w-full max-w-lg space-y-4 border border-black/10 p-4 shadow-soft"
          id={formId}
          onSubmit={handleSubmit}
        >
          <label className="block">
            <span className="mb-2 block text-sm font-semibold text-ink/70">
              Название проекта
            </span>
            <input
              autoComplete="off"
              className="ui-field"
              name="project-name"
              onChange={(event) => setName(event.target.value)}
              placeholder="Платформа аналитики"
              required
              value={name}
            />
          </label>
          <label className="block">
            <span className="mb-2 block text-sm font-semibold text-ink/70">
              Описание
            </span>
            <textarea
              className="ui-field min-h-28"
              name="project-description"
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Кратко опишите проект..."
              value={description}
            />
          </label>
          <button
            className="ui-button-primary"
            disabled={loading}
            type="submit"
          >
            {loading ? "Создаём..." : "Сохранить проект"}
          </button>
        </form>
      ) : null}
    </div>
  );
}
