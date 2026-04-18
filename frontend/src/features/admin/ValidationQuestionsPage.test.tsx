import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ValidationQuestionsPage from "@/features/admin/ValidationQuestionsPage";

const adminApiMock = vi.hoisted(() => ({
  deleteValidationQuestion: vi.fn(),
  listValidationQuestions: vi.fn(),
}));

const projectsApiMock = vi.hoisted(() => ({
  list: vi.fn(),
}));

vi.mock("@/api/adminApi", () => ({
  adminApi: adminApiMock,
}));

vi.mock("@/api/projectsApi", () => ({
  projectsApi: projectsApiMock,
}));

describe("ValidationQuestionsPage", () => {
  beforeEach(() => {
    adminApiMock.listValidationQuestions.mockResolvedValue({
      page: 1,
      page_size: 20,
      total: 1,
      items: [
        {
          id: "question-1",
          task_id: "task-1",
          project_id: "project-1",
          project_name: "Отчётность",
          task_title: "Сохранить фильтры отчёта",
          task_status: "needs_rework",
          tags: ["reports"],
          question_text: "Добавьте критерии приёмки или условия выполнения требования.",
          validation_verdict: "needs_rework",
          validated_at: new Date().toISOString(),
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ],
    });
    adminApiMock.deleteValidationQuestion.mockResolvedValue(undefined);
    projectsApiMock.list.mockResolvedValue([
      {
        id: "project-1",
        name: "Отчётность",
        description: "Дашборды",
        created_by: "user-1",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        validation_node_settings: {
          core_rules: true,
          custom_rules: true,
          context_questions: true,
        },
      },
    ]);
  });

  it("renders validation questions with task context", async () => {
    render(
      <MemoryRouter>
        <ValidationQuestionsPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Пул вопросов для разбора")).toBeInTheDocument();
    expect(screen.getByText("Сохранить фильтры отчёта")).toBeInTheDocument();
    expect(
      screen.getByText("Добавьте критерии приёмки или условия выполнения требования."),
    ).toBeInTheDocument();
    expect(screen.getByText("#reports")).toBeInTheDocument();
  });

  it("deletes a validation question after confirmation", async () => {
    render(
      <MemoryRouter>
        <ValidationQuestionsPage />
      </MemoryRouter>,
    );

    const deleteButton = await screen.findByRole("button", {
      name: "Удалить вопрос Сохранить фильтры отчёта",
    });
    fireEvent.click(deleteButton);
    fireEvent.click(screen.getByRole("button", { name: "Удалить" }));

    await waitFor(() => {
      expect(adminApiMock.deleteValidationQuestion).toHaveBeenCalledWith("question-1");
    });
  });
});
