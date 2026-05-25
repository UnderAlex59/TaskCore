import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
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

  it("shows task links only for explicitly used cross-task sources", () => {
    render(
      <MemoryRouter>
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
              cross_task_sources: [
                {
                  task_id: "task-3",
                  task_title: "Retry policy",
                },
              ],
              used_cross_task_sources: [
                {
                  chunk_id: "task-2:task_content:task-2:0",
                  task_id: "task-2",
                  task_title: "Status events",
                },
                {
                  chunk_id: "task-2:task_content:task-2:1",
                  task_id: "task-2",
                  task_title: "Status events",
                },
              ],
            },
          }}
          projectId="project-1"
        />
      </MemoryRouter>,
    );

    const sourceLink = screen.getByRole("link", {
      name: "Открыть задачу: Status events",
    });
    expect(sourceLink).toHaveAttribute(
      "href",
      "/projects/project-1/tasks/task-2",
    );
    expect(
      screen.queryByRole("link", { name: "Открыть задачу: Retry policy" }),
    ).not.toBeInTheDocument();
  });

  it("does not show task links from retrieval diagnostics only", () => {
    render(
      <MemoryRouter>
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
              cross_task_sources: [
                {
                  task_id: "task-3",
                  task_title: "Retry policy",
                },
              ],
            },
          }}
          projectId="project-1"
        />
      </MemoryRouter>,
    );

    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("renders proposal review messages as a summary without exposing the UUID", () => {
    render(
      <MessageBubble
        currentUserId="user-1"
        message={{
          ...baseMessage,
          agent_name: "ChangeTrackerAgent",
          author_id: null,
          author_name: null,
          content: "Предложение принято пользователем Admin.",
          message_type: "agent_proposal",
          source_ref: {
            collection: "change_proposals",
            proposal_id: "e3b01df2-3121-42a8-86d1-b9799d023f15",
            proposal_status: "accepted",
            proposal_text: "Добавить фильтр по статусу в отчет.",
            reviewed_by_name: "Admin",
          },
        }}
      />,
    );

    expect(screen.getByText("Предложение принято")).toBeInTheDocument();
    expect(screen.getByText("Принято")).toBeInTheDocument();
    expect(screen.getByText(/Решение принял: Admin\./)).toBeInTheDocument();
    expect(
      screen.getByText("Добавить фильтр по статусу в отчет."),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/e3b01df2-3121-42a8-86d1-b9799d023f15/),
    ).not.toBeInTheDocument();
  });

  it("hides the proposal UUID for legacy review message content", () => {
    render(
      <MessageBubble
        currentUserId="user-1"
        message={{
          ...baseMessage,
          agent_name: "ChangeTrackerAgent",
          author_id: null,
          author_name: null,
          content:
            "Предложение `e3b01df2-3121-42a8-86d1-b9799d023f15` переведено в статус `accepted` пользователем Admin.",
          message_type: "agent_proposal",
          source_ref: {
            collection: "change_proposals",
            proposal_id: "e3b01df2-3121-42a8-86d1-b9799d023f15",
          },
        }}
      />,
    );

    expect(screen.getByText("Предложение принято")).toBeInTheDocument();
    expect(screen.getByText("Принято")).toBeInTheDocument();
    expect(
      screen.queryByText(/e3b01df2-3121-42a8-86d1-b9799d023f15/),
    ).not.toBeInTheDocument();
  });
});
