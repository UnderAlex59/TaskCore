import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ProviderSettingsPage from "@/features/admin/ProviderSettingsPage";

const adminApiMock = vi.hoisted(() => ({
  createProvider: vi.fn(),
  getAudit: vi.fn(),
  listAvailableAgents: vi.fn(),
  getMonitoringActivity: vi.fn(),
  getMonitoringLlm: vi.fn(),
  getMonitoringSummary: vi.fn(),
  listOverrides: vi.fn(),
  listProviders: vi.fn(),
  setDefaultProvider: vi.fn(),
  testProvider: vi.fn(),
  updateOverride: vi.fn(),
  updateProvider: vi.fn(),
}));

vi.mock("@/api/adminApi", () => ({
  adminApi: adminApiMock,
}));

describe("ProviderSettingsPage", () => {
  beforeEach(() => {
    adminApiMock.listProviders.mockResolvedValue([
      {
        id: "provider-1",
        name: "Default provider",
        provider_kind: "openai",
        base_url: "https://api.openai.com/v1",
        model: "gpt-4o-mini",
        temperature: 0.2,
        enabled: true,
        input_cost_per_1k_tokens: null,
        output_cost_per_1k_tokens: null,
        secret_configured: true,
        masked_secret: "open****1234",
        is_default: true,
        used_by_agents: [],
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    ]);
    adminApiMock.listOverrides.mockResolvedValue([
      {
        agent_key: "qa",
        provider_config_id: "provider-1",
        provider_name: "Default provider",
        provider_kind: "openai",
        model: "gpt-4o-mini",
        enabled: true,
      },
    ]);
    adminApiMock.listAvailableAgents.mockResolvedValue([
      {
        key: "qa",
        name: "QAAgent",
        description: "Отвечает на вопросы по требованиям.",
        aliases: ["question"],
      },
      {
        key: "task-validation",
        name: "TaskValidationAgent",
        description: "Проверяет задачу по правилам валидации.",
        aliases: [],
      },
    ]);
    adminApiMock.setDefaultProvider.mockResolvedValue({});
    adminApiMock.testProvider.mockResolvedValue({
      ok: true,
      provider_kind: "openai",
      model: "gpt-4o-mini",
      latency_ms: 20,
      message: "Connectivity OK",
    });
    adminApiMock.updateOverride.mockResolvedValue({});
  });

  it("renders provider profiles and agent overrides", async () => {
    render(<ProviderSettingsPage />);

    expect(await screen.findByText("Default provider")).toBeInTheDocument();
    expect(
      screen.getByText("Специальные правила для сценариев"),
    ).toBeInTheDocument();
    expect(screen.getByText("QAAgent")).toBeInTheDocument();
    expect(screen.getByText("TaskValidationAgent")).toBeInTheDocument();
  });

  it("loads provider settings once on mount", async () => {
    render(<ProviderSettingsPage />);

    await screen.findByText("Default provider");
    await waitFor(() => {
      expect(adminApiMock.listProviders).toHaveBeenCalledTimes(2);
      expect(adminApiMock.listOverrides).toHaveBeenCalledTimes(2);
      expect(adminApiMock.listAvailableAgents).toHaveBeenCalledTimes(2);
    });
    await new Promise((resolve) => setTimeout(resolve, 50));

    expect(adminApiMock.listProviders).toHaveBeenCalledTimes(2);
    expect(adminApiMock.listOverrides).toHaveBeenCalledTimes(2);
    expect(adminApiMock.listAvailableAgents).toHaveBeenCalledTimes(2);
  });

  it("tests and promotes a provider", async () => {
    render(<ProviderSettingsPage />);

    const testButton = await screen.findByRole("button", {
      name: "Проверить подключение",
    });
    fireEvent.click(testButton);

    await waitFor(() => {
      expect(adminApiMock.testProvider).toHaveBeenCalledWith("provider-1");
    });

    const makeDefaultButton = screen.getByRole("button", {
      name: "Текущий профиль",
    });
    expect(makeDefaultButton).toBeDisabled();
  });
});
