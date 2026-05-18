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
export type PromptLogMode = "disabled" | "metadata_only" | "full";
export type LLMRequestStatus = "success" | "error";
export type GraphRunStatus = "running" | "success" | "error";
export type VisionSystemPromptMode = "system_role" | "inline_user";
export type VisionMessageOrder = "text_first" | "image_first";
export type VisionDetail = "default" | "auto" | "low" | "high";

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
  vision_enabled: boolean;
  vision_system_prompt_mode: VisionSystemPromptMode;
  vision_message_order: VisionMessageOrder;
  vision_detail: VisionDetail;
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
  vision_enabled: boolean;
  vision_system_prompt_mode: VisionSystemPromptMode;
  vision_message_order: VisionMessageOrder;
  vision_detail: VisionDetail;
  secret?: string;
}

export interface ProviderTestResult {
  ok: boolean;
  provider_kind: ProviderKind;
  model: string;
  latency_ms: number | null;
  message: string;
}

export interface VisionTestResult {
  ok: boolean;
  provider_config_id: string | null;
  provider_kind: string;
  provider_name: string | null;
  model: string;
  latency_ms: number | null;
  content_type: string;
  prompt: string;
  result_text: string | null;
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

export interface AgentPromptConfigRead {
  prompt_key: string;
  agent_key: string;
  name: string;
  aliases: string[];
  default_description: string;
  default_system_prompt: string;
  effective_description: string;
  effective_system_prompt: string;
  override_description: string | null;
  override_system_prompt: string | null;
  override_enabled: boolean;
  revision: number | null;
  updated_at: string | null;
}

export interface AgentPromptVersionRead {
  id: string;
  prompt_key: string;
  agent_key: string;
  description: string;
  system_prompt: string;
  enabled: boolean;
  revision: number;
  created_at: string;
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

export interface LLMRuntimeSettingsRead {
  prompt_log_mode: PromptLogMode;
  graph_monitoring_enabled: boolean;
}

export interface LLMRequestLogPageRead {
  page: number;
  page_size: number;
  total: number;
  prompt_log_mode: PromptLogMode;
  items: Array<{
    id: string;
    created_at: string;
    request_kind: string;
    actor_name: string;
    task_id: string | null;
    project_id: string | null;
    agent_key: string | null;
    graph_run_id: string | null;
    graph_node_name: string | null;
    provider_kind: string;
    model: string;
    status: LLMRequestStatus;
    latency_ms: number | null;
    prompt_tokens: number | null;
    completion_tokens: number | null;
    total_tokens: number | null;
    estimated_cost_usd: number | string | null;
    request_messages: Array<Record<string, unknown>> | null;
    response_text: string | null;
    error_message: string | null;
  }>;
}

export interface GraphRunSummaryRead {
  range: MonitoringRange;
  window_start: string;
  runs_total: number;
  success_total: number;
  error_total: number;
  running_total: number;
  error_rate: number;
  avg_latency_ms: number | null;
  slowest_graphs: Array<{
    graph_key: string;
    runs_total: number;
    avg_latency_ms: number | null;
    max_latency_ms: number | null;
  }>;
  recent_failures: Array<{
    id: string;
    graph_key: string;
    task_id: string | null;
    project_id: string | null;
    latency_ms: number | null;
    error_message: string | null;
    started_at: string;
  }>;
}

export interface GraphRunListItemRead {
  id: string;
  graph_key: string;
  status: GraphRunStatus;
  actor_name: string;
  actor_user_id: string | null;
  project_id: string | null;
  task_id: string | null;
  source: string | null;
  started_at: string;
  finished_at: string | null;
  latency_ms: number | null;
  error_message: string | null;
  events_count: number;
  llm_requests_count: number;
}

export interface GraphRunPageRead {
  page: number;
  page_size: number;
  total: number;
  items: GraphRunListItemRead[];
}

export interface GraphRunEventRead {
  id: string;
  sequence: number;
  event_type: string;
  node_name: string | null;
  namespace: string | null;
  status: GraphRunStatus;
  started_at: string;
  finished_at: string | null;
  latency_ms: number | null;
  payload: Record<string, unknown> | null;
  error_message: string | null;
}

export interface GraphRunNodeRead {
  id: string;
  sequence: number;
  graph_key: string | null;
  node_name: string;
  namespace: string | null;
  status: GraphRunStatus;
  latency_ms: number | null;
  input_preview: unknown;
  result_preview: unknown;
  error_message: string | null;
  llm_request_ids: string[];
  children: GraphRunNodeRead[];
}

export interface GraphRunTransitionRead {
  id: string;
  sequence: number;
  graph_key: string | null;
  namespace: string | null;
  source_node: string | null;
  condition: string | null;
  reason: string | null;
  condition_input_preview: unknown;
  selected: string[];
  target_nodes: string[];
}

export interface GraphRunGraphNodeRead {
  mermaid_id: string;
  node_event_id: string | null;
  node_name: string;
  graph_key: string;
  executed: boolean;
}

export interface GraphRunGraphViewRead {
  graph_key: string;
  mermaid: string;
  nodes: GraphRunGraphNodeRead[];
  executed_node_ids: string[];
  executed_edge_ids: string[];
  selected_edge_ids: string[];
}

export interface GraphRunDetailRead extends Omit<
  GraphRunListItemRead,
  "events_count" | "llm_requests_count"
> {
  input_preview: Record<string, unknown> | null;
  final_state_preview: Record<string, unknown> | null;
  events: GraphRunEventRead[];
  node_tree: GraphRunNodeRead[];
  transitions: GraphRunTransitionRead[];
  graph_views: GraphRunGraphViewRead[];
  llm_requests: LLMRequestLogPageRead["items"];
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

export type QdrantScenario =
  | "related_tasks"
  | "project_questions"
  | "duplicate_proposal"
  | "qa_rag_chunks";
export type QdrantHeuristicStatus = "ok" | "warning";
export type QdrantMatchBand =
  | "above_threshold"
  | "near_threshold"
  | "below_threshold";

export interface QdrantCollectionDiagnosticRead {
  collection_name: string;
  exists: boolean;
  status: string | null;
  points_count: number | null;
  vectors_count: number | null;
  indexed_vectors_count: number | null;
  segments_count: number | null;
  vector_size: number | null;
  distance: string | null;
  metadata: Record<string, string>;
  sample_payload_keys: string[];
  provider_matches: boolean | null;
  model_matches: boolean | null;
  vector_size_matches: boolean | null;
  metadata_matches_active_embeddings: boolean | null;
  warnings: string[];
  error: string | null;
}

export interface QdrantOverviewRead {
  connected: boolean;
  connection_error: string | null;
  qdrant_url: string;
  embedding_provider: string | null;
  embedding_model: string | null;
  expected_vector_size: number | null;
  generated_at: string;
  collections: QdrantCollectionDiagnosticRead[];
}

export interface QdrantScenarioHeuristicRead {
  code: string;
  status: QdrantHeuristicStatus;
  message: string;
}

export interface QdrantScenarioResultRead {
  id: string;
  task_id: string | null;
  task_title: string | null;
  task_status: string | null;
  score: number | null;
  snippet: string;
  metadata: Record<string, unknown> | null;
  match_band: QdrantMatchBand | null;
}

export interface QdrantRagChunkResultRead {
  id: string;
  scope: "current_task_attachment" | "cross_task";
  selected_for_prompt: boolean;
  confidence: number;
  score: number;
  threshold: number;
  match_band: QdrantMatchBand;
  content: string;
  task_id: string | null;
  task_title: string | null;
  task_status: string | null;
  source_type: string | null;
  chunk_kind: string | null;
  chunk_index: number | null;
  source_id: string | null;
  filename: string | null;
  metadata: Record<string, unknown>;
}

export interface QdrantScenarioProbeRead {
  scenario: QdrantScenario;
  project_id: string;
  task_id: string | null;
  query_text: string;
  heuristic_status: QdrantHeuristicStatus;
  heuristics: QdrantScenarioHeuristicRead[];
  results: QdrantScenarioResultRead[];
  raw_threshold: number | null;
  rag_chunks: QdrantRagChunkResultRead[];
}

export interface QdrantCoverageTaskRead {
  id: string;
  title: string;
  status: TaskStatus;
  indexed_at: string | null;
  updated_at: string;
  embeddings_stale: boolean;
  requires_revalidation: boolean;
  validation_questions_total: number;
  knowledge_points_count: number;
  question_points_count: number;
}

export interface QdrantProjectCoverageRead {
  project_id: string;
  project_name: string;
  generated_at: string;
  summary: {
    tasks_total: number;
    indexed_tasks_total: number;
    stale_tasks_total: number;
    tasks_with_knowledge_total: number;
    tasks_with_questions_total: number;
  };
  items: QdrantCoverageTaskRead[];
}

export interface QdrantTaskResyncRead {
  task_id: string;
  project_id: string;
  indexed_at: string | null;
  embeddings_stale: boolean;
  knowledge_points_count: number;
  question_points_count: number;
  chunk_ids: string[];
  warnings: string[];
}

export type AdaptationEvalRunStatus =
  | "queued"
  | "running"
  | "success"
  | "error";
export type AdaptationEvalCaseResultStatus = "passed" | "failed" | "error";
export type AdaptationEvalScenarioType =
  | "positive"
  | "negative_control"
  | "partial_match"
  | "noise"
  | "regression";
export type AdaptationEvalVerdict = "approved" | "needs_rework";
export type AdaptationEvalExportArtifact = "case_results" | "metrics";

export interface AdaptationEvalHistoricalTaskPayload {
  title: string;
  content: string;
  tags: string[];
  chat_messages: string[];
}

export interface AdaptationEvalProbeTaskPayload {
  title: string;
  content: string;
  tags: string[];
  custom_rules?: Array<Record<string, unknown>>;
  related_tasks?: Array<Record<string, unknown>>;
  attachment_names?: string[];
}

export interface AdaptationEvalCasePayload {
  external_id: string;
  scenario_type: AdaptationEvalScenarioType;
  historical_tasks: AdaptationEvalHistoricalTaskPayload[];
  probe_task: AdaptationEvalProbeTaskPayload;
  expected_captured_questions: string[];
  expected_retrieved_questions: string[];
  expected_context_questions: string[];
  expected_verdict: AdaptationEvalVerdict;
  expected_context_issues: Array<Record<string, unknown>>;
  metadata: Record<string, unknown>;
}

export interface AdaptationEvalImportPayload {
  dataset_name: string;
  project_id: string;
  cases: AdaptationEvalCasePayload[];
}

export interface AdaptationEvalQualityGates {
  capture_recall_min: number;
  retrieval_recall_at_k_min: number;
  context_question_f1_min: number;
  context_issue_f1_min: number;
  duplicate_rate_max: number;
  require_full_improvement: boolean;
}

export interface AdaptationEvalRunConfig {
  retrieval_limit: number;
  cleanup_synthetic_tasks: boolean;
  quality_gates: AdaptationEvalQualityGates;
}

export interface AdaptationEvalDatasetRead {
  id: string;
  project_id: string;
  project_name: string | null;
  name: string;
  cases_total: number;
  last_run_id: string | null;
  last_run_status: AdaptationEvalRunStatus | null;
  created_at: string;
  updated_at: string;
}

export interface AdaptationEvalCaseRead extends AdaptationEvalCasePayload {
  id: string;
  updated_at: string;
}

export interface AdaptationEvalDatasetDetailRead
  extends AdaptationEvalDatasetRead {
  cases: AdaptationEvalCaseRead[];
}

export interface AdaptationEvalImportResultRead {
  dataset: AdaptationEvalDatasetDetailRead;
  imported_cases: number;
  warnings: string[];
}

export interface AdaptationEvalRunCreateRead {
  id: string;
  dataset_id: string;
  status: AdaptationEvalRunStatus;
  config: AdaptationEvalRunConfig;
  created_at: string;
}

export interface AdaptationEvalRunListItemRead {
  id: string;
  dataset_id: string;
  dataset_name: string | null;
  project_id: string;
  status: AdaptationEvalRunStatus;
  config: AdaptationEvalRunConfig;
  summary_metrics: Record<string, unknown> | null;
  started_at: string | null;
  finished_at: string | null;
  latency_ms: number | null;
  error_message: string | null;
  created_at: string;
}

export interface AdaptationEvalRunPageRead {
  page: number;
  page_size: number;
  total: number;
  items: AdaptationEvalRunListItemRead[];
}

export interface AdaptationEvalCaseResultRead {
  id: string;
  case_id: string;
  case_external_id: string;
  scenario_type: string;
  status: AdaptationEvalCaseResultStatus;
  core_graph_run_id: string | null;
  full_graph_run_id: string | null;
  synthetic_task_ids: string[];
  expected_result: Record<string, unknown>;
  actual_result: Record<string, unknown>;
  diffs: Record<string, unknown>;
  metrics: Record<string, unknown>;
  latency_ms: number | null;
  error_message: string | null;
  created_at: string;
}

export interface AdaptationEvalRunRead extends AdaptationEvalRunListItemRead {
  case_results: AdaptationEvalCaseResultRead[];
}

export type RagEvalImportFormat = "json" | "csv";
export type RagEvalRunStatus = "queued" | "running" | "success" | "error";
export type RagEvalIndexingMode = "all" | "stale_only" | "none";

export interface RagEvalRunConfig {
  indexing_mode: RagEvalIndexingMode;
  retrieval_limit: number;
  use_query_rewriter: boolean;
  use_hybrid_rerank: boolean;
  include_cross_task: boolean;
  include_current_task_content: boolean;
  run_answer_agent: boolean;
  run_llm_judge: boolean;
  min_score_override: number | null;
}

export interface RagEvalImportPayload {
  format: RagEvalImportFormat;
  dataset_name?: string | null;
  project_id?: string | null;
  content?: string | null;
  payload?: {
    dataset_name: string;
    project_id: string;
    tasks: Array<{
      external_id: string;
      title: string;
      content: string;
      tags?: string[];
      attachments?: Array<{
        filename: string;
        content_type?: string;
        content: string;
      }> | null;
    }>;
    cases: Array<{
      external_id: string;
      task_external_id: string;
      question: string;
      expected_answer?: string | null;
      expected_relevant?: Array<{
        task_external_id?: string | null;
        source_type?: string | null;
        chunk_index?: number | null;
        text_contains?: string | null;
      }>;
    }>;
  } | null;
}

export interface RagEvalDatasetRead {
  id: string;
  project_id: string;
  project_name: string | null;
  name: string;
  tasks_total: number;
  cases_total: number;
  last_run_id: string | null;
  last_run_status: RagEvalRunStatus | null;
  created_at: string;
  updated_at: string;
}

export interface RagEvalDatasetDetailRead extends RagEvalDatasetRead {
  tasks: Array<{
    id: string;
    external_id: string;
    task_id: string;
    title: string;
    updated_at: string;
  }>;
  cases: Array<{
    id: string;
    external_id: string;
    task_external_id: string;
    task_id: string;
    question: string;
    expected_answer: string | null;
    expected_relevant: Array<Record<string, unknown>>;
    updated_at: string;
  }>;
}

export interface RagEvalImportResultRead {
  dataset: RagEvalDatasetDetailRead;
  created_tasks: number;
  updated_tasks: number;
  imported_cases: number;
  warnings: string[];
}

export interface RagEvalRunCreateRead {
  id: string;
  dataset_id: string;
  status: RagEvalRunStatus;
  config: RagEvalRunConfig;
  created_at: string;
}

export interface RagEvalRunListItemRead {
  id: string;
  dataset_id: string;
  dataset_name: string | null;
  project_id: string;
  status: RagEvalRunStatus;
  config: RagEvalRunConfig;
  summary_metrics: Record<string, unknown> | null;
  started_at: string | null;
  finished_at: string | null;
  latency_ms: number | null;
  error_message: string | null;
  created_at: string;
}

export interface RagEvalRunPageRead {
  page: number;
  page_size: number;
  total: number;
  items: RagEvalRunListItemRead[];
}

export interface RagEvalRunRead {
  id: string;
  dataset_id: string;
  dataset_name: string | null;
  project_id: string;
  status: RagEvalRunStatus;
  config: RagEvalRunConfig;
  summary_metrics: Record<string, unknown> | null;
  started_at: string | null;
  finished_at: string | null;
  latency_ms: number | null;
  error_message: string | null;
  created_at: string;
  index_results: Array<{
    id: string;
    task_id: string;
    task_external_id: string;
    status: string;
    attachment_payload_ms: number | null;
    chunking_ms: number | null;
    embedding_and_qdrant_write_ms: number | null;
    qdrant_cleanup_ms: number | null;
    total_index_ms: number | null;
    chunks_total: number;
    error_message: string | null;
    created_at: string;
  }>;
  case_results: Array<{
    id: string;
    case_id: string;
    case_external_id: string;
    question: string;
    task_id: string;
    task_external_id: string;
    status: string;
    retrieved_chunks: Array<Record<string, unknown>>;
    matched_expected: Array<Record<string, unknown>>;
    answer_text: string | null;
    answer_source_ref: Record<string, unknown> | null;
    judge_payload: Record<string, unknown> | null;
    metrics: Record<string, unknown>;
    latency_ms: number | null;
    retrieval_latency_ms: number | null;
    answer_latency_ms: number | null;
    judge_latency_ms: number | null;
    error_message: string | null;
    created_at: string;
  }>;
}

export type OrchestratorEvalImportFormat = "json" | "csv";
export type OrchestratorEvalRunStatus =
  | "queued"
  | "running"
  | "success"
  | "error";
export type OrchestratorEvalCaseStatus = "passed" | "failed" | "error";
export type OrchestratorRoutingMode = "auto" | "forced";
export type OrchestratorMessageType =
  | "general"
  | "question"
  | "change_proposal";

export interface OrchestratorEvalExpectedRoute {
  ai_response_required?: boolean | null;
  target_agent_key?: string | null;
  message_type?: OrchestratorMessageType | null;
  routing_mode?: OrchestratorRoutingMode | null;
  reason_contains?: string | null;
}

export interface OrchestratorEvalInput {
  project_id: string;
  task_id?: string | null;
  task_title: string;
  task_status: string;
  task_content: string;
  validation_result?: Record<string, unknown> | null;
  message_content: string;
  requested_agent?: string | null;
}

export interface OrchestratorEvalRunConfig {
  compare_reason: boolean;
}

export interface OrchestratorEvalPlaygroundRunPayload {
  input: OrchestratorEvalInput;
  expected_route?: OrchestratorEvalExpectedRoute | null;
  config: OrchestratorEvalRunConfig;
}

export interface OrchestratorEvalImportPayload {
  format: OrchestratorEvalImportFormat;
  dataset_name?: string | null;
  project_id?: string | null;
  content?: string | null;
  payload?: {
    dataset_name: string;
    project_id: string;
    cases: Array<{
      external_id: string;
      input: OrchestratorEvalInput;
      expected_route?: OrchestratorEvalExpectedRoute;
    }>;
  } | null;
}

export interface OrchestratorEvalDatasetRead {
  id: string;
  project_id: string;
  project_name: string | null;
  name: string;
  cases_total: number;
  last_run_id: string | null;
  last_run_status: OrchestratorEvalRunStatus | null;
  created_at: string;
  updated_at: string;
}

export interface OrchestratorEvalCaseRead {
  id: string;
  external_id: string;
  input: OrchestratorEvalInput;
  expected_route: Record<string, unknown>;
  updated_at: string;
}

export interface OrchestratorEvalDatasetDetailRead extends OrchestratorEvalDatasetRead {
  cases: OrchestratorEvalCaseRead[];
}

export interface OrchestratorEvalImportResultRead {
  dataset: OrchestratorEvalDatasetDetailRead;
  imported_cases: number;
  warnings: string[];
}

export interface OrchestratorEvalPlaygroundResultRead {
  status: OrchestratorEvalCaseStatus;
  input: OrchestratorEvalInput;
  expected_route: Record<string, unknown>;
  actual_route: Record<string, unknown>;
  metrics: Record<string, unknown>;
  graph_run_id: string | null;
  latency_ms: number | null;
  error_message: string | null;
}

export interface OrchestratorEvalCaseResultRead extends OrchestratorEvalPlaygroundResultRead {
  id: string;
  case_id: string;
  case_external_id: string;
  created_at: string;
}

export interface OrchestratorEvalRunCreateRead {
  id: string;
  dataset_id: string;
  status: OrchestratorEvalRunStatus;
  config: OrchestratorEvalRunConfig;
  created_at: string;
}

export interface OrchestratorEvalRunListItemRead {
  id: string;
  dataset_id: string;
  dataset_name: string | null;
  project_id: string;
  status: OrchestratorEvalRunStatus;
  config: OrchestratorEvalRunConfig;
  summary_metrics: Record<string, unknown> | null;
  started_at: string | null;
  finished_at: string | null;
  latency_ms: number | null;
  error_message: string | null;
  created_at: string;
}

export interface OrchestratorEvalRunPageRead {
  page: number;
  page_size: number;
  total: number;
  items: OrchestratorEvalRunListItemRead[];
}

export interface OrchestratorEvalRunRead extends Omit<
  OrchestratorEvalRunListItemRead,
  "summary_metrics"
> {
  summary_metrics: Record<string, unknown> | null;
  case_results: OrchestratorEvalCaseResultRead[];
}

export type ValidationEvalImportFormat = "json" | "csv";
export type ValidationEvalRunStatus =
  | "queued"
  | "running"
  | "success"
  | "error";
export type ValidationEvalCaseResultStatus = "passed" | "failed" | "error";
export type ValidationEvalVerdict = "approved" | "needs_rework";
export type ValidationEvalSeverity = "low" | "medium" | "high";
export type ValidationEvalExportArtifact =
  | "case_results"
  | "metrics"
  | "confusion_matrix"
  | "ablation"
  | "errors";

export interface ValidationEvalExpectedIssue extends Record<string, unknown> {
  code?: string | null;
  severity?: ValidationEvalSeverity | null;
  message: string;
  rule_title?: string | null;
  source?: string | null;
}

export interface ValidationEvalCustomRule extends Record<string, unknown> {
  title: string;
  description: string;
  applies_to_tags: string[];
}

export interface ValidationEvalCasePayload {
  external_id: string;
  title: string;
  content: string;
  tags: string[];
  attachment_names: string[];
  custom_rules: ValidationEvalCustomRule[];
  related_tasks: Array<Record<string, unknown>>;
  historical_questions: string[];
  expected_verdict: ValidationEvalVerdict;
  expected_issues: ValidationEvalExpectedIssue[];
  expected_questions: string[];
  expected_context_questions: string[];
  metadata: Record<string, unknown>;
}

export interface ValidationEvalStructuredImport {
  dataset_name: string;
  project_id: string;
  cases: ValidationEvalCasePayload[];
}

export interface ValidationEvalImportPayload {
  format: ValidationEvalImportFormat;
  dataset_name?: string | null;
  project_id?: string | null;
  content?: string | null;
  payload?: ValidationEvalStructuredImport | null;
}

export interface ValidationEvalVariantConfig {
  key: string;
  label?: string | null;
  validation_node_settings: Record<string, boolean>;
  provider_config_id?: string | null;
  prompt_version_ids: Record<string, string>;
}

export interface ValidationEvalRunConfig {
  variants: ValidationEvalVariantConfig[];
  run_question_judge: boolean;
}

export interface ValidationEvalDatasetRead {
  id: string;
  project_id: string;
  project_name: string | null;
  name: string;
  cases_total: number;
  last_run_id: string | null;
  last_run_status: ValidationEvalRunStatus | null;
  created_at: string;
  updated_at: string;
}

export interface ValidationEvalCaseRead extends ValidationEvalCasePayload {
  id: string;
  updated_at: string;
}

export interface ValidationEvalDatasetDetailRead extends ValidationEvalDatasetRead {
  cases: ValidationEvalCaseRead[];
}

export interface ValidationEvalImportResultRead {
  dataset: ValidationEvalDatasetDetailRead;
  imported_cases: number;
  warnings: string[];
}

export interface ValidationEvalRunCreateRead {
  id: string;
  dataset_id: string;
  status: ValidationEvalRunStatus;
  config: ValidationEvalRunConfig;
  created_at: string;
}

export interface ValidationEvalRunListItemRead {
  id: string;
  dataset_id: string;
  dataset_name: string | null;
  project_id: string;
  status: ValidationEvalRunStatus;
  config: ValidationEvalRunConfig;
  summary_metrics: Record<string, unknown> | null;
  started_at: string | null;
  finished_at: string | null;
  latency_ms: number | null;
  error_message: string | null;
  created_at: string;
}

export interface ValidationEvalRunPageRead {
  page: number;
  page_size: number;
  total: number;
  items: ValidationEvalRunListItemRead[];
}

export interface ValidationEvalCaseResultRead {
  id: string;
  case_id: string;
  case_external_id: string;
  variant_key: string;
  variant_label: string | null;
  status: ValidationEvalCaseResultStatus;
  graph_run_id: string | null;
  judge_graph_run_id: string | null;
  expected_result: Record<string, unknown>;
  actual_result: Record<string, unknown>;
  diffs: Record<string, unknown>;
  judge_payload: Record<string, unknown> | null;
  metrics: Record<string, unknown>;
  latency_ms: number | null;
  error_message: string | null;
  created_at: string;
}

export interface ValidationEvalRunRead extends ValidationEvalRunListItemRead {
  case_results: ValidationEvalCaseResultRead[];
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
  testVision: async (file: File, prompt: string) => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("prompt", prompt);
    return (
      await apiClient.post<VisionTestResult>(
        "/admin/llm/vision-test",
        formData,
        {
          headers: { "Content-Type": "multipart/form-data" },
        },
      )
    ).data;
  },
  setDefaultProvider: async (providerConfigId: string) =>
    (
      await apiClient.post<ProviderConfigRead>(
        "/admin/llm/runtime/default-provider",
        {
          provider_config_id: providerConfigId,
        },
      )
    ).data,
  getLlmRuntimeSettings: async () =>
    (await apiClient.get<LLMRuntimeSettingsRead>("/admin/llm/runtime/settings"))
      .data,
  updateLlmRuntimeSettings: async (
    settings:
      | PromptLogMode
      | {
          graph_monitoring_enabled?: boolean;
          prompt_log_mode?: PromptLogMode;
        },
  ) =>
    (
      await apiClient.patch<LLMRuntimeSettingsRead>(
        "/admin/llm/runtime/settings",
        typeof settings === "string" ? { prompt_log_mode: settings } : settings,
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
  listPromptConfigs: async () =>
    (await apiClient.get<AgentPromptConfigRead[]>("/admin/llm/prompt-configs"))
      .data,
  updatePromptConfig: async (
    promptKey: string,
    payload: { description: string; enabled: boolean; system_prompt: string },
  ) =>
    (
      await apiClient.patch<AgentPromptConfigRead>(
        `/admin/llm/prompt-configs/${promptKey}`,
        payload,
      )
    ).data,
  listPromptVersions: async (promptKey: string) =>
    (
      await apiClient.get<AgentPromptVersionRead[]>(
        `/admin/llm/prompt-configs/${promptKey}/versions`,
      )
    ).data,
  restorePromptVersion: async (promptKey: string, versionId: string) =>
    (
      await apiClient.post<AgentPromptConfigRead>(
        `/admin/llm/prompt-configs/${promptKey}/restore`,
        { version_id: versionId },
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
  getLlmRequestLogs: async (
    range: MonitoringRange,
    page = 1,
    status?: LLMRequestStatus,
  ) =>
    (
      await apiClient.get<LLMRequestLogPageRead>(
        "/admin/monitoring/llm/requests",
        {
          params: { range, page, status },
        },
      )
    ).data,
  getGraphRunSummary: async (range: MonitoringRange) =>
    (
      await apiClient.get<GraphRunSummaryRead>(
        "/admin/monitoring/graphs/summary",
        { params: { range } },
      )
    ).data,
  getGraphRuns: async (params: {
    graph_key?: string;
    page?: number;
    project_id?: string;
    range: MonitoringRange;
    status?: GraphRunStatus;
    task_id?: string;
  }) =>
    (
      await apiClient.get<GraphRunPageRead>("/admin/monitoring/graphs/runs", {
        params,
      })
    ).data,
  getGraphRunDetail: async (runId: string) =>
    (
      await apiClient.get<GraphRunDetailRead>(
        `/admin/monitoring/graphs/runs/${runId}`,
      )
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
  getQdrantOverview: async () =>
    (await apiClient.get<QdrantOverviewRead>("/admin/qdrant/overview")).data,
  getQdrantProjectCoverage: async (projectId: string, limit = 20) =>
    (
      await apiClient.get<QdrantProjectCoverageRead>(
        `/admin/qdrant/projects/${projectId}/coverage`,
        { params: { limit } },
      )
    ).data,
  probeQdrantRelatedTasks: async (payload: {
    project_id: string;
    task_id?: string;
    query_text?: string;
    exclude_task_id?: string;
    limit?: number;
  }) =>
    (
      await apiClient.post<QdrantScenarioProbeRead>(
        "/admin/qdrant/scenarios/related-tasks",
        payload,
      )
    ).data,
  probeQdrantProjectQuestions: async (payload: {
    project_id: string;
    task_id?: string;
    query_text?: string;
    tags?: string[];
    limit?: number;
  }) =>
    (
      await apiClient.post<QdrantScenarioProbeRead>(
        "/admin/qdrant/scenarios/project-questions",
        payload,
      )
    ).data,
  probeQdrantQaRagChunks: async (payload: {
    project_id: string;
    question: string;
    task_id?: string;
    limit?: number;
  }) =>
    (
      await apiClient.post<QdrantScenarioProbeRead>(
        "/admin/qdrant/scenarios/qa-rag-chunks",
        payload,
      )
    ).data,
  probeQdrantDuplicateProposal: async (payload: {
    project_id: string;
    proposal_text: string;
    task_id?: string;
  }) =>
    (
      await apiClient.post<QdrantScenarioProbeRead>(
        "/admin/qdrant/scenarios/duplicate-proposal",
        payload,
      )
    ).data,
  resyncQdrantTask: async (taskId: string) =>
    (
      await apiClient.post<QdrantTaskResyncRead>(
        `/admin/qdrant/tasks/${taskId}/resync`,
      )
    ).data,
  listRagEvalDatasets: async () =>
    (await apiClient.get<RagEvalDatasetRead[]>("/admin/rag-eval/datasets"))
      .data,
  importRagEvalDataset: async (payload: RagEvalImportPayload) =>
    (
      await apiClient.post<RagEvalImportResultRead>(
        "/admin/rag-eval/datasets/import",
        payload,
      )
    ).data,
  getRagEvalDataset: async (datasetId: string) =>
    (
      await apiClient.get<RagEvalDatasetDetailRead>(
        `/admin/rag-eval/datasets/${datasetId}`,
      )
    ).data,
  createRagEvalRun: async (datasetId: string, config: RagEvalRunConfig) =>
    (
      await apiClient.post<RagEvalRunCreateRead>(
        `/admin/rag-eval/datasets/${datasetId}/runs`,
        config,
      )
    ).data,
  listRagEvalRuns: async (
    datasetId: string,
    params: {
      page?: number;
      size?: number;
      status?: RagEvalRunStatus;
    } = {},
  ) =>
    (
      await apiClient.get<RagEvalRunPageRead>(
        `/admin/rag-eval/datasets/${datasetId}/runs`,
        { params },
      )
    ).data,
  getRagEvalRun: async (runId: string) =>
    (await apiClient.get<RagEvalRunRead>(`/admin/rag-eval/runs/${runId}`)).data,
  deleteRagEvalRun: async (runId: string) => {
    await apiClient.delete(`/admin/rag-eval/runs/${runId}`);
  },
  exportRagEvalRun: async (runId: string, format: "json" | "csv") =>
    (
      await apiClient.get<string>(`/admin/rag-eval/runs/${runId}/export`, {
        params: { format },
        responseType: "text",
      })
    ).data,
  runOrchestratorEvalPlayground: async (
    payload: OrchestratorEvalPlaygroundRunPayload,
  ) =>
    (
      await apiClient.post<OrchestratorEvalPlaygroundResultRead>(
        "/admin/orchestrator-eval/playground/run",
        payload,
      )
    ).data,
  listOrchestratorEvalDatasets: async () =>
    (
      await apiClient.get<OrchestratorEvalDatasetRead[]>(
        "/admin/orchestrator-eval/datasets",
      )
    ).data,
  importOrchestratorEvalDataset: async (
    payload: OrchestratorEvalImportPayload,
  ) =>
    (
      await apiClient.post<OrchestratorEvalImportResultRead>(
        "/admin/orchestrator-eval/datasets/import",
        payload,
      )
    ).data,
  getOrchestratorEvalDataset: async (datasetId: string) =>
    (
      await apiClient.get<OrchestratorEvalDatasetDetailRead>(
        `/admin/orchestrator-eval/datasets/${datasetId}`,
      )
    ).data,
  createOrchestratorEvalRun: async (
    datasetId: string,
    config: OrchestratorEvalRunConfig,
  ) =>
    (
      await apiClient.post<OrchestratorEvalRunCreateRead>(
        `/admin/orchestrator-eval/datasets/${datasetId}/runs`,
        config,
      )
    ).data,
  listOrchestratorEvalRuns: async (
    datasetId: string,
    params: {
      page?: number;
      size?: number;
      status?: OrchestratorEvalRunStatus;
    } = {},
  ) =>
    (
      await apiClient.get<OrchestratorEvalRunPageRead>(
        `/admin/orchestrator-eval/datasets/${datasetId}/runs`,
        { params },
      )
    ).data,
  getOrchestratorEvalRun: async (runId: string) =>
    (
      await apiClient.get<OrchestratorEvalRunRead>(
        `/admin/orchestrator-eval/runs/${runId}`,
      )
    ).data,
  deleteOrchestratorEvalRun: async (runId: string) => {
    await apiClient.delete(`/admin/orchestrator-eval/runs/${runId}`);
  },
  exportOrchestratorEvalRun: async (runId: string, format: "json" | "csv") =>
    (
      await apiClient.get<string>(
        `/admin/orchestrator-eval/runs/${runId}/export`,
        {
          params: { format },
          responseType: "text",
        },
      )
    ).data,
  listAdaptationEvalDatasets: async () =>
    (
      await apiClient.get<AdaptationEvalDatasetRead[]>(
        "/admin/adaptation-eval/datasets",
      )
    ).data,
  getAdaptationEvalImportTemplate: async (projectId?: string) =>
    (
      await apiClient.get<AdaptationEvalImportPayload>(
        "/admin/adaptation-eval/datasets/import",
        { params: projectId ? { project_id: projectId } : undefined },
      )
    ).data,
  importAdaptationEvalDataset: async (
    payload: AdaptationEvalImportPayload,
  ) =>
    (
      await apiClient.post<AdaptationEvalImportResultRead>(
        "/admin/adaptation-eval/datasets/import",
        payload,
      )
    ).data,
  getAdaptationEvalDataset: async (datasetId: string) =>
    (
      await apiClient.get<AdaptationEvalDatasetDetailRead>(
        `/admin/adaptation-eval/datasets/${datasetId}`,
      )
    ).data,
  deleteAdaptationEvalDataset: async (datasetId: string) => {
    await apiClient.delete(`/admin/adaptation-eval/datasets/${datasetId}`);
  },
  createAdaptationEvalRun: async (
    datasetId: string,
    config: AdaptationEvalRunConfig,
  ) =>
    (
      await apiClient.post<AdaptationEvalRunCreateRead>(
        `/admin/adaptation-eval/datasets/${datasetId}/runs`,
        config,
      )
    ).data,
  listAdaptationEvalRuns: async (
    datasetId: string,
    params: {
      page?: number;
      size?: number;
      status?: AdaptationEvalRunStatus;
    } = {},
  ) =>
    (
      await apiClient.get<AdaptationEvalRunPageRead>(
        `/admin/adaptation-eval/datasets/${datasetId}/runs`,
        { params },
      )
    ).data,
  getAdaptationEvalRun: async (runId: string) =>
    (
      await apiClient.get<AdaptationEvalRunRead>(
        `/admin/adaptation-eval/runs/${runId}`,
      )
    ).data,
  deleteAdaptationEvalRun: async (runId: string) => {
    await apiClient.delete(`/admin/adaptation-eval/runs/${runId}`);
  },
  exportAdaptationEvalRun: async (
    runId: string,
    artifact: AdaptationEvalExportArtifact,
    format: "json" | "csv",
  ) =>
    (
      await apiClient.get<string>(
        `/admin/adaptation-eval/runs/${runId}/export`,
        {
          params: { artifact, format },
          responseType: "text",
        },
      )
    ).data,
  listValidationEvalDatasets: async () =>
    (
      await apiClient.get<ValidationEvalDatasetRead[]>(
        "/admin/validation-eval/datasets",
      )
    ).data,
  importValidationEvalDataset: async (payload: ValidationEvalImportPayload) =>
    (
      await apiClient.post<ValidationEvalImportResultRead>(
        "/admin/validation-eval/datasets/import",
        payload,
      )
    ).data,
  getValidationEvalDataset: async (datasetId: string) =>
    (
      await apiClient.get<ValidationEvalDatasetDetailRead>(
        `/admin/validation-eval/datasets/${datasetId}`,
      )
    ).data,
  deleteValidationEvalDataset: async (datasetId: string) => {
    await apiClient.delete(`/admin/validation-eval/datasets/${datasetId}`);
  },
  createValidationEvalCase: async (
    datasetId: string,
    payload: ValidationEvalCasePayload,
  ) =>
    (
      await apiClient.post<ValidationEvalCaseRead>(
        `/admin/validation-eval/datasets/${datasetId}/cases`,
        payload,
      )
    ).data,
  updateValidationEvalCase: async (
    datasetId: string,
    caseId: string,
    payload: Partial<ValidationEvalCasePayload>,
  ) =>
    (
      await apiClient.patch<ValidationEvalCaseRead>(
        `/admin/validation-eval/datasets/${datasetId}/cases/${caseId}`,
        payload,
      )
    ).data,
  deleteValidationEvalCase: async (datasetId: string, caseId: string) => {
    await apiClient.delete(
      `/admin/validation-eval/datasets/${datasetId}/cases/${caseId}`,
    );
  },
  createValidationEvalRun: async (
    datasetId: string,
    config: ValidationEvalRunConfig,
  ) =>
    (
      await apiClient.post<ValidationEvalRunCreateRead>(
        `/admin/validation-eval/datasets/${datasetId}/runs`,
        config,
      )
    ).data,
  listValidationEvalRuns: async (
    datasetId: string,
    params: {
      page?: number;
      size?: number;
      status?: ValidationEvalRunStatus;
    } = {},
  ) =>
    (
      await apiClient.get<ValidationEvalRunPageRead>(
        `/admin/validation-eval/datasets/${datasetId}/runs`,
        { params },
      )
    ).data,
  getValidationEvalRun: async (runId: string) =>
    (
      await apiClient.get<ValidationEvalRunRead>(
        `/admin/validation-eval/runs/${runId}`,
      )
    ).data,
  deleteValidationEvalRun: async (runId: string) => {
    await apiClient.delete(`/admin/validation-eval/runs/${runId}`);
  },
  exportValidationEvalRun: async (
    runId: string,
    artifact: ValidationEvalExportArtifact,
    format: "json" | "csv",
  ) =>
    (
      await apiClient.get<string>(
        `/admin/validation-eval/runs/${runId}/export`,
        {
          params: { artifact, format },
          responseType: "text",
        },
      )
    ).data,
};
