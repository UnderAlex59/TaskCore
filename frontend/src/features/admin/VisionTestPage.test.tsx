import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import VisionTestPage from "@/features/admin/VisionTestPage";

const adminApiMock = vi.hoisted(() => ({
  testVision: vi.fn(),
}));

vi.mock("@/api/adminApi", () => ({
  adminApi: adminApiMock,
}));

describe("VisionTestPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    adminApiMock.testVision.mockResolvedValue({
      ok: true,
      provider_config_id: "provider-1",
      provider_kind: "openai",
      provider_name: "Vision provider",
      model: "gpt-4o",
      latency_ms: 88,
      content_type: "image/png",
      prompt: "Извлеки текст",
      result_text: "Счет №42\nИтого: 15 000 ₽",
      message: "Счет №42\nИтого: 15 000 ₽",
    });
  });

  it("runs vision test and renders extracted text", async () => {
    render(<VisionTestPage />);

    const file = new File(["png-bytes"], "scan.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText("Файл изображения"), {
      target: { files: [file] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Запустить Vision-тест" }));

    await waitFor(() => {
      expect(adminApiMock.testVision).toHaveBeenCalledWith(
        file,
        expect.stringContaining("Извлеки весь читаемый текст"),
      );
    });

    expect(await screen.findByText("Vision provider")).toBeInTheDocument();
    expect(screen.getAllByText(/Счет №42/)).toHaveLength(2);
    expect(screen.getAllByText(/Итого: 15 000 ₽/)).toHaveLength(2);
  });

  it("shows validation error when file is missing", async () => {
    render(<VisionTestPage />);

    fireEvent.click(screen.getByRole("button", { name: "Запустить Vision-тест" }));

    expect(
      await screen.findByText("Выберите изображение для проверки."),
    ).toBeInTheDocument();
    expect(adminApiMock.testVision).not.toHaveBeenCalled();
  });
});
