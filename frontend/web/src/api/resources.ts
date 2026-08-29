import type { PlatformRun } from "@/types/planning";

export const resourcesApi = {
  fromRun: (run: PlatformRun | null) => (run?.resources || null) as Record<string, unknown> | null,
};
