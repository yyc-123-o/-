import { api } from "./client";

export type LearnerTheme = "light" | "dark" | "system";

export interface LearnerPreferences {
  reminders_enabled: boolean;
  theme: LearnerTheme;
  updated_at: string;
}

export const settingsApi = {
  get: (learnerId: string) =>
    api.get<LearnerPreferences>(`/api/v1/learners/${encodeURIComponent(learnerId)}/preferences`).then((r) => r.data),
  update: (learnerId: string, payload: Pick<LearnerPreferences, "reminders_enabled" | "theme">) =>
    api.put<LearnerPreferences>(`/api/v1/learners/${encodeURIComponent(learnerId)}/preferences`, payload).then((r) => r.data),
};
