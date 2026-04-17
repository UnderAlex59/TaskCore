import { render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import MessageList from "@/features/chat/MessageList";

const baseMessage = {
  id: "message-1",
  task_id: "task-1",
  author_id: "user-1",
  author_name: "Alex Analyst",
  author_avatar_url: null,
  agent_name: null,
  message_type: "user",
  content: "Initial message",
  source_ref: null,
  created_at: new Date("2026-04-14T10:00:00.000Z").toISOString(),
};

const originalScrollIntoView = HTMLElement.prototype.scrollIntoView;

describe("MessageList", () => {
  beforeEach(() => {
    HTMLElement.prototype.scrollIntoView = vi.fn();
  });

  afterEach(() => {
    HTMLElement.prototype.scrollIntoView = originalScrollIntoView;
  });

  it("scrolls to the latest message on initial render and updates", async () => {
    const { rerender } = render(<MessageList messages={[baseMessage]} />);

    await waitFor(() => {
      expect(HTMLElement.prototype.scrollIntoView).toHaveBeenCalledTimes(1);
    });

    rerender(
      <MessageList
        messages={[
          baseMessage,
          {
            ...baseMessage,
            id: "message-2",
            content: "Follow-up message",
            created_at: new Date("2026-04-14T10:05:00.000Z").toISOString(),
          },
        ]}
      />,
    );

    await waitFor(() => {
      expect(HTMLElement.prototype.scrollIntoView).toHaveBeenCalledTimes(2);
    });
  });
});
