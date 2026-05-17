import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { ValidationResult } from "@/api/tasksApi";
import ValidationPanel from "@/features/tasks/ValidationPanel";

const needsReworkResult: ValidationResult = {
  verdict: "needs_rework",
  issues: [
    {
      finding_id: "finding-1",
      source: "context_questions",
      code: "context_question",
      severity: "medium",
      message: "Какие статусы считаются терминальными?",
    },
  ],
  questions: [],
  validated_at: "2026-05-16T10:00:00.000Z",
};

describe("ValidationPanel", () => {
  it("requires selecting every issue and entering reasons before appeal submit", async () => {
    const user = userEvent.setup();
    const onAppeal = vi.fn(async () => undefined);

    render(
      <ValidationPanel
        canAppeal
        onAppeal={onAppeal}
        result={needsReworkResult}
      />,
    );

    expect(screen.getByText("Апелляция")).toBeInTheDocument();
    const submitButton = screen.getByRole("button", {
      name: "Отклонить рекомендации",
    });
    expect(submitButton).toBeDisabled();

    await user.click(
      screen.getByRole("checkbox", {
        name: "Какие статусы считаются терминальными?",
      }),
    );
    await user.type(
      screen.getByLabelText("Причина отклонения"),
      "Риск принят аналитиком.",
    );

    expect(submitButton).toBeEnabled();
    await user.click(submitButton);

    await waitFor(() => {
      expect(onAppeal).toHaveBeenCalledWith([
        {
          finding_id: "finding-1",
          reason: "Риск принят аналитиком.",
        },
      ]);
    });
  });

  it("shows accepted appeal items as read-only skipped findings", () => {
    render(
      <ValidationPanel
        result={{
          ...needsReworkResult,
          verdict: "approved",
          issues: [],
          automated_verdict: "needs_rework",
          appeal: {
            status: "accepted",
            appealed_at: "2026-05-16T10:05:00.000Z",
            appealed_by: "user-1",
            items: [
              {
                finding_id: "finding-1",
                source: "context_questions",
                code: "context_question",
                severity: "medium",
                message: "Какие статусы считаются терминальными?",
                reason: "Риск принят аналитиком.",
              },
            ],
          },
        }}
      />,
    );

    expect(screen.getByText("Пропущенные замечания системы")).toBeInTheDocument();
    expect(screen.getByText(/Причина: Риск принят аналитиком/)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Отклонить рекомендации" }),
    ).not.toBeInTheDocument();
  });
});
