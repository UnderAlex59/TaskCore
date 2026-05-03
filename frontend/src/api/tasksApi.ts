import { apiClient } from "@/api/client";

export interface ValidationResult {
  verdict: "approved" | "needs_rework";
  issues: Array<{
    code: string;
    message: string;
    severity: "low" | "medium" | "high";
  }>;
  questions: string[];
  validated_at: string;
}

export interface TaskTagSuggestionItem {
  tag: string;
  confidence: number;
  reason: string;
}

export interface TaskTagSuggestionRequest {
  title: string;
  content: string;
  current_tags: string[];
}

export interface TaskTagSuggestionResponse {
  suggestions: TaskTagSuggestionItem[];
  generated_at: string;
}

export interface TaskRead {
  id: string;
  project_id: string;
  title: string;
  content: string;
  tags: string[];
  status: TaskStatus;
  created_by: string;
  analyst_id: string;
  reviewer_analyst_id: string | null;
  developer_id: string | null;
  tester_id: string | null;
  reviewer_approved_at: string | null;
  validation_result: ValidationResult | null;
  attachments: TaskAttachmentRead[];
  indexed_at: string | null;
  embeddings_stale: boolean;
  requires_revalidation: boolean;
  created_at: string;
  updated_at: string;
}

export interface TaskCreate {
  title: string;
  content?: string;
  tags?: string[];
}

export type TaskUpdate = TaskCreate;

export interface TaskApprove {
  developer_id?: string | null;
  tester_id?: string | null;
  reviewer_analyst_id?: string | null;
}

export interface TaskAttachmentRead {
  id: string;
  task_id: string;
  filename: string;
  content_type: string;
  storage_path: string;
  alt_text: string | null;
  created_at: string;
}

export type TaskStatus =
  | "draft"
  | "validating"
  | "needs_rework"
  | "awaiting_approval"
  | "ready_for_dev"
  | "in_progress"
  | "ready_for_testing"
  | "testing"
  | "done";

export interface TaskListParams {
  analyst_id?: string;
  developer_id?: string;
  page?: number;
  search?: string;
  size?: number;
  status?: TaskStatus;
  tags?: string[];
  tester_id?: string;
}

export const tasksApi = {
  list: async (projectId: string, params?: TaskListParams) =>
    (await apiClient.get<TaskRead[]>(`/projects/${projectId}/tasks`, { params })).data,
  create: async (projectId: string, payload: TaskCreate) =>
    (await apiClient.post<TaskRead>(`/projects/${projectId}/tasks`, payload)).data,
  get: async (projectId: string, taskId: string) =>
    (await apiClient.get<TaskRead>(`/projects/${projectId}/tasks/${taskId}`)).data,
  update: async (projectId: string, taskId: string, payload: Partial<TaskCreate>) =>
    (await apiClient.patch<TaskRead>(`/projects/${projectId}/tasks/${taskId}`, payload)).data,
  commitChanges: async (projectId: string, taskId: string) =>
    (await apiClient.post<TaskRead>(`/projects/${projectId}/tasks/${taskId}/commit`)).data,
  approve: async (projectId: string, taskId: string, payload: TaskApprove) =>
    (await apiClient.post<TaskRead>(`/projects/${projectId}/tasks/${taskId}/approve`, payload)).data,
  startDevelopment: async (projectId: string, taskId: string) =>
    (await apiClient.post<TaskRead>(`/projects/${projectId}/tasks/${taskId}/start-development`)).data,
  markReadyForTesting: async (projectId: string, taskId: string) =>
    (await apiClient.post<TaskRead>(`/projects/${projectId}/tasks/${taskId}/ready-for-testing`)).data,
  startTesting: async (projectId: string, taskId: string) =>
    (await apiClient.post<TaskRead>(`/projects/${projectId}/tasks/${taskId}/start-testing`)).data,
  complete: async (projectId: string, taskId: string) =>
    (await apiClient.post<TaskRead>(`/projects/${projectId}/tasks/${taskId}/complete`)).data,
  remove: async (projectId: string, taskId: string) => {
    await apiClient.delete(`/projects/${projectId}/tasks/${taskId}`);
  },
  validate: async (taskId: string) => (await apiClient.post<ValidationResult>(`/tasks/${taskId}/validate`)).data,
  uploadAttachment: async (projectId: string, taskId: string, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return (
      await apiClient.post<TaskAttachmentRead>(`/projects/${projectId}/tasks/${taskId}/attachments`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      })
    ).data;
  },
  getAttachmentBlob: async (projectId: string, taskId: string, attachmentId: string) =>
    (
      await apiClient.get<Blob>(
        `/projects/${projectId}/tasks/${taskId}/attachments/${attachmentId}`,
        { responseType: "blob" },
      )
    ).data,
  deleteAttachment: async (projectId: string, taskId: string, attachmentId: string) => {
    await apiClient.delete(`/projects/${projectId}/tasks/${taskId}/attachments/${attachmentId}`);
  },
  suggestTags: async (
    projectId: string,
    taskId: string,
    payload: TaskTagSuggestionRequest,
  ) =>
    (
      await apiClient.post<TaskTagSuggestionResponse>(
        `/projects/${projectId}/tasks/${taskId}/suggest-tags`,
        payload,
      )
    ).data,
};
