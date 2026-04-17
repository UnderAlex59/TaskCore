import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import TaskForm from "@/features/tasks/TaskForm";

const baseTask = {
  id: "task-1",
  project_id: "project-1",
  title: "Preserve report filters",
  content: "When a user refreshes the page, saved report filters must remain available.",
  tags: ["reports"],
  status: "draft" as const,
  created_by: "analyst-1",
  analyst_id: "analyst-1",
  developer_id: null,
  tester_id: null,
  validation_result: null,
  attachments: [],
  created_at: new Date("2026-04-16T08:00:00.000Z").toISOString(),
  updated_at: new Date("2026-04-16T08:00:00.000Z").toISOString(),
};

describe("TaskForm", () => {
  it("submits only editable task fields and does not render the old assignee selector", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);

    render(<TaskForm onSubmit={onSubmit} task={baseTask} />);

    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();

    const titleInput = screen.getByRole("textbox", { name: "Название" });
    await user.clear(titleInput);
    await user.type(titleInput, "Approved workflow");

    await user.click(screen.getByRole("button", { name: "Сохранить задачу" }));

    expect(onSubmit).toHaveBeenCalledWith({
      title: "Approved workflow",
      content: baseTask.content,
      tags: baseTask.tags,
    });
  });
});
