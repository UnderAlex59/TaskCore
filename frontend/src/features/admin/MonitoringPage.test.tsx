import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import MonitoringPage from "@/features/admin/MonitoringPage";

const adminApiMock = vi.hoisted(() => ({
  getAudit: vi.fn(),
  getMonitoringActivity: vi.fn(),
  getMonitoringLlm: vi.fn(),
  getMonitoringSummary: vi.fn(),
}));

vi.mock("@/api/adminApi", () => ({
  adminApi: adminApiMock,
}));

describe("MonitoringPage", () => {
  beforeEach(() => {
    adminApiMock.getMonitoringSummary.mockResolvedValue({
      range: "7d",
      window_start: new Date().toISOString(),
      generated_at: new Date().toISOString(),
      all_time: {
        users_total: 3,
        active_users_total: 2,
        projects_total: 1,
        tasks_total: 5,
        messages_total: 8,
        proposals_total: 2,
        validations_total: 1,
      },
      range_metrics: {
        active_users: 2,
        audit_events_total: 12,
        llm_requests_total: 4,
        llm_error_rate: 0.25,
        avg_llm_latency_ms: 180,
        estimated_llm_cost_usd: 0.12,
      },
    });
    adminApiMock.getMonitoringActivity.mockResolvedValue({
      range: "7d",
      window_start: new Date().toISOString(),
      buckets: [
        {
          day: "2026-04-10",
          events_total: 4,
          logins: 1,
          task_mutations: 2,
          validation_runs: 1,
          proposal_reviews: 0,
          admin_changes: 0,
        },
      ],
      top_actors: [{ user_id: "1", full_name: "Admin User", event_count: 4 }],
      top_actions: [{ event_type: "auth.login.success", count: 1 }],
    });
    adminApiMock.getMonitoringLlm.mockResolvedValue({
      range: "7d",
      window_start: new Date().toISOString(),
      requests_total: 4,
      success_total: 3,
      error_total: 1,
      avg_latency_ms: 180,
      estimated_cost_usd: 0.12,
      provider_breakdown: [{ provider_kind: "openai", request_count: 4 }],
      daily: [{ day: "2026-04-10", total: 4, providers: { openai: 4 } }],
      recent_failures: [],
    });
    adminApiMock.getAudit.mockResolvedValue({
      page: 1,
      page_size: 20,
      total: 2,
      items: [
        {
          id: "event-1",
          created_at: new Date().toISOString(),
          actor_name: "Admin User",
          event_type: "auth.login.success",
          entity_type: "session",
          entity_id: "session-1",
          project_id: null,
          task_id: null,
          metadata: null,
        },
      ],
    });
  });

  it("renders summary metrics and monitoring sections", async () => {
    render(<MonitoringPage />);

    expect(await screen.findByText("System visibility")).toBeInTheDocument();
    expect(screen.getByText("Daily operational activity")).toBeInTheDocument();
    expect(screen.getByText("Recent audit feed")).toBeInTheDocument();
    expect(screen.getByText("Admin User")).toBeInTheDocument();
  });

  it("loads monitoring data once on mount", async () => {
    render(<MonitoringPage />);

    await screen.findByText("System visibility");
    await waitFor(() => {
      expect(adminApiMock.getMonitoringSummary).toHaveBeenCalledTimes(2);
      expect(adminApiMock.getMonitoringActivity).toHaveBeenCalledTimes(2);
      expect(adminApiMock.getMonitoringLlm).toHaveBeenCalledTimes(2);
      expect(adminApiMock.getAudit).toHaveBeenCalledTimes(2);
    });
    await new Promise((resolve) => setTimeout(resolve, 50));

    expect(adminApiMock.getMonitoringSummary).toHaveBeenCalledTimes(2);
    expect(adminApiMock.getMonitoringActivity).toHaveBeenCalledTimes(2);
    expect(adminApiMock.getMonitoringLlm).toHaveBeenCalledTimes(2);
    expect(adminApiMock.getAudit).toHaveBeenCalledTimes(2);
  });
});
