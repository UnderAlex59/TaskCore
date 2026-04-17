import { useEffect, useState } from "react";

import type { TaskRead, TaskUpdate } from "@/api/tasksApi";

interface Props {
  disabled?: boolean;
  loading?: boolean;
  onSubmit: (payload: TaskUpdate) => Promise<void>;
  task: TaskRead;
}

export default function TaskForm({
  task,
  onSubmit,
  disabled = false,
  loading = false,
}: Props) {
  const [title, setTitle] = useState(task.title);
  const [content, setContent] = useState(task.content);
  const [tags, setTags] = useState(task.tags.join(", "));

  useEffect(() => {
    setTitle(task.title);
    setContent(task.content);
    setTags(task.tags.join(", "));
  }, [task]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onSubmit({
      title,
      content,
      tags: tags
        .split(",")
        .map((tag) => tag.trim())
        .filter(Boolean),
    });
  }

  return (
    <form className="space-y-4" onSubmit={handleSubmit}>
      <div>
        <p className="text-sm font-semibold text-ink">Редактор задачи</p>
        <p className="mt-1 text-sm text-ink/60">
          Редактирование доступно, пока задача остается черновиком или требует
          доработки. Команда задачи формируется отдельным подтверждением после
          ревью.
        </p>
      </div>
      <label className="block">
        <span className="mb-2 block text-sm font-semibold text-ink/70">
          Название
        </span>
        <input
          className="ui-field"
          disabled={disabled}
          name="task-title"
          onChange={(event) => setTitle(event.target.value)}
          value={title}
        />
      </label>
      <label className="block">
        <span className="mb-2 block text-sm font-semibold text-ink/70">
          Текст требования
        </span>
        <textarea
          className="ui-field min-h-44"
          disabled={disabled}
          name="task-content"
          onChange={(event) => setContent(event.target.value)}
          value={content}
        />
      </label>
      <label className="block">
        <span className="mb-2 block text-sm font-semibold text-ink/70">
          Теги
        </span>
        <input
          className="ui-field"
          disabled={disabled}
          name="task-tags"
          onChange={(event) => setTags(event.target.value)}
          placeholder="Теги через запятую"
          value={tags}
        />
      </label>
      <button className="ui-button-primary" disabled={disabled || loading} type="submit">
        {loading ? "Сохраняем..." : "Сохранить задачу"}
      </button>
    </form>
  );
}
