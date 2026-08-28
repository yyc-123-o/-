import { api } from "./client";

export const assessmentApi = {
  submit: (runId: string, payload: Record<string, unknown>) =>
    api.post(`/api/v1/runs/${encodeURIComponent(runId)}/assessment`, payload).then((r) => r.data),
  practiceReview: (runId: string, payload: Record<string, unknown>) =>
    api.post(`/api/v1/runs/${encodeURIComponent(runId)}/practice-review`, payload).then((r) => r.data),
};
