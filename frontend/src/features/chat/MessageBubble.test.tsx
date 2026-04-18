import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import MessageBubble from "@/features/chat/MessageBubble";

const baseMessage = {
  id: "message-1",
  task_id: "task-1",
  author_id: "user-1",
  author_name: "Alex Analyst",
  author_avatar_url: null,
  agent_name: null,
  message_type: "general",
  content: "Initial message",
  source_ref: null,
  created_at: new Date("2026-04-14T10:00:00.000Z").toISOString(),
};

describe("MessageBubble", () => {
  it("renders the current user's message on the right", () => {
    const { container } = render(
      <MessageBubble currentUserId="user-1" message={baseMessage} />,
    );

    expect(container.firstChild).toHaveClass("justify-end");
  });

  it("renders other users' messages on the left", () => {
    const { container } = render(
      <MessageBubble currentUserId="user-2" message={baseMessage} />,
    );

    expect(container.firstChild).toHaveClass("justify-start");
    expect(screen.getByText("Alex Analyst")).toBeInTheDocument();
  });
});
