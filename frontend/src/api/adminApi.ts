import { apiClient } from "@/api/client";
import type { TaskTagOption } from "@/api/taskTagsApi";
import type { TaskStatus, ValidationResult } from "@/api/tasksApi";

export type ProviderKind =
  | "openai"
  | "ollama"
  | "openrouter"
  | "gigachat"
  | "openai_compatible";
export type MonitoringRange = "24h" | "7d" | "30d" | "90d";

export interface ProviderConfigRead {
  id: string;
  name: string;
  provider_kind: ProviderKind;
  base_url: string;
  model: string;
  temperature: number;
  enabled: boolean;
  input_cost_per_1k_tokens: number | string | null;
  output_cost_per_1k_tokens: number | string | null;
  secret_configured: boolean;
  masked_secret: string | null;
  is_default: boolean;
  used_by_agents: string[];
  created_at: string;
  updated_at: string;
}

export interface ProviderConfigPayload {
  name: string;
  provider_kind: ProviderKind;
  base_url: string | null;
  model: string;
  temperature: number;
  enabled: boolean;
  input_cost_per_1k_tokens: number | null;
  output_cost_per_1k_tokens: number | null;
  secret?: string;
}

export interface ProviderTestResult {
  ok: boolean;
  provider_kind: ProviderKind;
  model: string;
  latency_ms: number | null;
  message: string;
}

export interface AgentOverrideRead {
  agent_key: string;
  provider_config_id: string;
  provider_name: string;
  provider_kind: ProviderKind;
  model: string;
  enabled: boolean;
}

export interface AgentDirectoryRead {
  key: string;
  name: string;
  description: string;
  aliases: string[];
}

export interface MonitoringSummaryRead {
  range: MonitoringRange;
  window_start: string;
  generated_at: string;
  all_time: {
    users_total: number;
    active_users_total: number;
    projects_total: number;
    tasks_total: number;
    messages_total: number;
    proposals_total: number;
    validations_total: number;
  };
  range_metrics: {
    active_users: number;
    audit_events_total: number;
    llm_requests_total: number;
    llm_error_rate: number;
    avg_llm_latency_ms: number | null;
    estimated_llm_cost_usd: number | string | null;
  };
}

export interface MonitoringActivityRead {
  range: MonitoringRange;
  window_start: string;
  buckets: Array<{
    day: string;
    events_total: number;
    logins: number;
    task_mutations: number;
    validation_runs: number;
    proposal_reviews: number;
    admin_changes: number;
  }>;
  top_actors: Array<{
    user_id: string | null;
    full_name: string;
    event_count: number;
  }>;
  top_actions: Array<{
    event_type: string;
    count: number;
  }>;
}

export interface MonitoringLLMRead {
  range: MonitoringRange;
  window_start: string;
  requests_total: number;
  success_total: number;
  error_total: number;
  avg_latency_ms: number | null;
  estimated_cost_usd: number | string | null;
  provider_breakdown: Array<{
    provider_kind: string;
    request_count: number;
  }>;
  daily: Array<{
    day: string;
    total: number;
    providers: Record<string, number>;
  }>;
  recent_failures: Array<{
    id: string;
    created_at: string;
    agent_key: string | null;
    actor_name: string;
    provider_kind: string;
    model: string;
    error_message: string | null;
  }>;
}

export interface AuditPageRead {
  page: number;
  page_size: number;
  total: number;
  items: Array<{
    id: string;
    created_at: string;
    actor_name: string;
    event_type: string;
    entity_type: string;
    entity_id: string | null;
    project_id: string | null;
    task_id: string | null;
    metadata: Record<string, unknown> | null;
  }>;
}

export interface ValidationQuestionRead {
  id: string;
  task_id: string;
  project_id: string;
  project_name: string;
  task_title: string;
  task_status: TaskStatus;
  tags: string[];
  question_text: string;
  validation_verdict: ValidationResult["verdict"];
  validated_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ValidationQuestionPageRead {
  page: number;
  page_size: number;
  total: number;
  items: ValidationQuestionRead[];
}

export interface AdminTaskTagRead extends TaskTagOption {
  created_by: string;
  created_at: string;
  updated_at: string;
  tasks_count: number;
  rules_count: number;
}

export interface ValidationQuestionListParams {
  page?: number;
  project_id?: string;
  search?: string;
  size?: number;
  tag?: string;
  task_status?: TaskStatus;
  verdict?: ValidationResult["verdict"];
}

export const adminApi = {
  listProviders: async () =>
    (await apiClient.get<ProviderConfigRead[]>("/admin/llm/providers")).data,
  createProvider: async (payload: ProviderConfigPayload) =>
    (await apiClient.post<ProviderConfigRead>("/admin/llm/providers", payload))
      .data,
  updateProvider: async (
    providerId: string,
    payload: Partial<ProviderConfigPayload>,
  ) =>
    (
      await apiClient.patch<ProviderConfigRead>(
        `/admin/llm/providers/${providerId}`,
        payload,
      )
    ).data,
  testProvider: async (providerId: string) =>
    (
      await apiClient.post<ProviderTestResult>(
        `/admin/llm/providers/${providerId}/test`,
      )
    ).data,
  setDefaultProvider: async (providerConfigId: string) =>
    (
      await apiClient.post<ProviderConfigRead>(
        "/admin/llm/runtime/default-provider",
        {
          provider_config_id: providerConfigId,
        },
      )
    ).data,
  listOverrides: async () =>
    (await apiClient.get<AgentOverrideRead[]>("/admin/llm/overrides")).data,
  listAvailableAgents: async () =>
    (await apiClient.get<AgentDirectoryRead[]>("/admin/llm/agents")).data,
  updateOverride: async (
    agentKey: string,
    providerConfigId: string,
    enabled: boolean,
  ) =>
    (
      await apiClient.put<AgentOverrideRead>(
        `/admin/llm/overrides/${agentKey}`,
        {
          provider_config_id: providerConfigId,
          enabled,
        },
      )
    ).data,
  getMonitoringSummary: async (range: MonitoringRange) =>
    (
      await apiClient.get<MonitoringSummaryRead>("/admin/monitoring/summary", {
        params: { range },
      })
    ).data,
  getMonitoringActivity: async (range: MonitoringRange) =>
    (
      await apiClient.get<MonitoringActivityRead>(
        "/admin/monitoring/activity",
        { params: { range } },
      )
    ).data,
  getMonitoringLlm: async (range: MonitoringRange) =>
    (
      await apiClient.get<MonitoringLLMRead>("/admin/monitoring/llm", {
        params: { range },
      })
    ).data,
  getAudit: async (range: MonitoringRange, page = 1) =>
    (
      await apiClient.get<AuditPageRead>("/admin/audit", {
        params: { range, page },
      })
    ).data,
  listValidationQuestions: async (params?: ValidationQuestionListParams) =>
    (
      await apiClient.get<ValidationQuestionPageRead>(
        "/admin/validation/questions",
        {
          params,
        },
      )
    ).data,
  deleteValidationQuestion: async (questionId: string) => {
    await apiClient.delete(`/admin/validation/questions/${questionId}`);
  },
  listTaskTags: async () =>
    (await apiClient.get<AdminTaskTagRead[]>("/admin/task-tags")).data,
  createTaskTag: async (name: string) =>
    (await apiClient.post<AdminTaskTagRead>("/admin/task-tags", { name })).data,
  updateTaskTag: async (tagId: string, name: string) =>
    (
      await apiClient.patch<AdminTaskTagRead>(`/admin/task-tags/${tagId}`, {
        name,
      })
    ).data,
  deleteTaskTag: async (tagId: string) => {
    await apiClient.delete(`/admin/task-tags/${tagId}`);
  },
};
