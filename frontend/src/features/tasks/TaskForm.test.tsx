import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import TaskForm from "@/features/tasks/TaskForm";
import { buildTaskDocumentFromEditors } from "@/features/tasks/taskDocument";

const baseTask = {
  id: "task-1",
  project_id: "project-1",
  title: "Preserve report filters",
  content:
    "When a user refreshes the page, saved report filters must remain available.",
  tags: ["Reports"],
  status: "draft" as const,
  created_by: "analyst-1",
  analyst_id: "analyst-1",
  developer_id: null,
  tester_id: null,
  validation_result: null,
  attachments: [],
  indexed_at: null,
  embeddings_stale: true,
  requires_revalidation: false,
  created_at: new Date("2026-04-16T08:00:00.000Z").toISOString(),
  updated_at: new Date("2026-04-16T08:00:00.000Z").toISOString(),
};

const availableTags = [
  { id: "reports", name: "Reports" },
  { id: "analytics", name: "Analytics" },
];

describe("TaskForm", () => {
  it("submits task content from the single document editor", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);

    render(
      <TaskForm
        availableTags={availableTags}
        onSubmit={onSubmit}
        task={baseTask}
      />,
    );

    const titleInput = screen.getByRole("textbox", {
      name: "Название задачи",
    });
    await user.clear(titleInput);
    await user.type(titleInput, "Approved workflow");

    const documentInput = screen.getByRole("textbox", {
      name: "Текст задачи",
    });
    await user.clear(documentInput);
    await user.type(
      documentInput,
      "## Описание\nApproved workflow body\n\n## Acceptance criteria\nFilter preset is restored after refresh.",
    );

    await user.click(screen.getByRole("button", { name: "Теги: Reports" }));
    await user.click(screen.getByRole("checkbox", { name: "Analytics" }));
    await user.click(
      screen.getByRole("button", { name: "Сохранить страницу" }),
    );

    expect(onSubmit).toHaveBeenCalledWith({
      title: "Approved workflow",
      content: buildTaskDocumentFromEditors(
        "## Описание\nApproved workflow body\n\n## Acceptance criteria\nFilter preset is restored after refresh.",
        "",
      ),
      tags: ["Reports", "Analytics"],
    });
  });

  it("keeps history changes in a separate pane and blocks commit when they are unsaved", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const onCommit = vi.fn().mockResolvedValue(undefined);

    render(
      <TaskForm
        activePane="history"
        availableTags={availableTags}
        canCommitChanges
        embeddingsStale
        onCommit={onCommit}
        onSubmit={onSubmit}
        task={{
          ...baseTask,
          status: "ready_for_dev",
          indexed_at: new Date("2026-04-16T09:00:00.000Z").toISOString(),
        }}
      />,
    );

    const commitButton = screen.getByRole("button", {
      name: "Commit изменений",
    });
    expect(commitButton).toBeEnabled();

    await user.type(
      screen.getByRole("textbox", { name: "История изменений" }),
      "19.04 — Added clarification for refresh behavior.",
    );

    expect(commitButton).toBeDisabled();

    const saveButton = screen.getByRole("button", {
      name: "Сохранить страницу",
    });
    expect(saveButton).toBeEnabled();

    await user.click(saveButton);
    expect(onSubmit).toHaveBeenCalledOnce();
    expect(onCommit).not.toHaveBeenCalled();
  });
});
