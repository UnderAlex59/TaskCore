import { apiClient } from "@/api/client";

export interface ProposalRead {
  id: string;
  task_id: string;
  source_message_id: string | null;
  proposed_by: string | null;
  proposed_by_name: string | null;
  proposal_text: string;
  status: string;
  reviewed_by: string | null;
  reviewed_by_name: string | null;
  reviewed_at: string | null;
  created_at: string;
}

export interface ProposalUpdate {
  status: "accepted" | "rejected";
}

export const proposalsApi = {
  list: async (taskId: string, status?: string) =>
    (await apiClient.get<ProposalRead[]>(`/tasks/${taskId}/proposals`, { params: { status } })).data,
  update: async (taskId: string, proposalId: string, payload: ProposalUpdate) =>
    (await apiClient.patch<ProposalRead>(`/tasks/${taskId}/proposals/${proposalId}`, payload)).data,
};
