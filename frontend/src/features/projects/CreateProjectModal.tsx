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
        className="ui-button-primary"
        onClick={() => setOpen((current) => !current)}
        type="button"
      >
        {open ? "Скрыть форму" : "Создать проект"}
      </button>

      {open ? (
        <form
          className="w-full max-w-xl space-y-4 rounded-[18px] border border-[rgba(9,30,66,0.12)] bg-[#fafbfc] p-5"
          id={formId}
          onSubmit={handleSubmit}
        >
          <label className="block">
            <span className="mb-2 block text-sm font-semibold text-[#172b4d]">
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
            <span className="mb-2 block text-sm font-semibold text-[#172b4d]">
              Описание
            </span>
            <textarea
              className="ui-field min-h-28"
              name="project-description"
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Кратко опишите назначение проекта и состав команды."
              value={description}
            />
          </label>
          <div className="flex flex-wrap gap-3">
            <button
              className="ui-button-primary"
              disabled={loading}
              type="submit"
            >
              {loading ? "Создаем..." : "Сохранить проект"}
            </button>
            <button
              className="ui-button-ghost"
              onClick={() => setOpen(false)}
              type="button"
            >
              Отмена
            </button>
          </div>
        </form>
      ) : null}
    </div>
  );
}
