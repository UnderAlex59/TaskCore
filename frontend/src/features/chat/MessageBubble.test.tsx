import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

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

  it("marks agent messages with agent metadata", () => {
    render(
      <MessageBubble
        currentUserId="user-1"
        message={{
          ...baseMessage,
          agent_name: "QAAgent",
          author_id: null,
          author_name: null,
          message_type: "agent_answer",
          source_ref: {
            agent_description: "Отвечает на вопросы по требованиям.",
            agent_key: "qa",
          },
        }}
      />,
    );

    expect(screen.getByText("Агент вопросов")).toBeInTheDocument();
    expect(screen.getByText("Агент")).toBeInTheDocument();
    expect(
      screen.getByText("Отвечает на вопросы по требованиям."),
    ).toBeInTheDocument();
  });

  it("shows analyst request action for confident QA answers", () => {
    const onRequestAnalyst = vi.fn();

    render(
      <MessageBubble
        currentUserId="user-1"
        message={{
          ...baseMessage,
          agent_name: "QAAgent",
          author_id: null,
          author_name: null,
          message_type: "agent_answer",
          source_ref: {
            agent_key: "qa",
            answer_confidence: "high",
          },
        }}
        onRequestAnalyst={onRequestAnalyst}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Позвать аналитика" }));

    expect(onRequestAnalyst).toHaveBeenCalledTimes(1);
  });

  it("hides analyst request action for low confidence QA answers", () => {
    render(
      <MessageBubble
        currentUserId="user-1"
        message={{
          ...baseMessage,
          agent_name: "QAAgent",
          author_id: null,
          author_name: null,
          message_type: "agent_answer",
          source_ref: {
            agent_key: "qa",
            answer_confidence: "low",
          },
        }}
        onRequestAnalyst={vi.fn()}
      />,
    );

    expect(
      screen.queryByRole("button", { name: "Позвать аналитика" }),
    ).not.toBeInTheDocument();
  });
});
