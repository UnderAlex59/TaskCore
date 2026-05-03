import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { TaskAttachmentRead } from "@/api/tasksApi";
import AttachmentUpload from "@/features/tasks/AttachmentUpload";

const attachment: TaskAttachmentRead = {
  id: "attachment-1",
  task_id: "task-1",
  filename: "oauth_pattern_learning.png",
  content_type: "image/png",
  storage_path: "tasks/task-1/oauth_pattern_learning.png",
  alt_text: "Диаграмма описывает систему семантического поиска решений.",
  created_at: new Date("2026-05-03T08:00:00.000Z").toISOString(),
};

describe("AttachmentUpload", () => {
  it("hides attachment alt-text until the user opens it", async () => {
    const user = userEvent.setup();

    render(
      <AttachmentUpload
        attachments={[attachment]}
        onDelete={vi.fn()}
        onUpload={vi.fn()}
      />,
    );

    expect(
      screen.queryByText(attachment.alt_text as string),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Показать alt-text" }));

    expect(screen.getByText(attachment.alt_text as string)).toBeInTheDocument();
  });
});
