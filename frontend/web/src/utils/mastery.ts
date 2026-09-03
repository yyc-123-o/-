export type MasteryValue = number | null | undefined;

export type MasteryBand =
  | "unknown"
  | "very-low"
  | "low"
  | "medium"
  | "high";

export interface MasteryVisual {
  background: string;
  border: string;
  color: string;
  accent: string;
  borderStyle: "solid" | "dashed";
  opacity: number;
}

const MASTERY_COLORS: Record<Exclude<MasteryBand, "unknown">, string> = {
  "very-low": "#d9eef1",
  low: "#a8dce2",
  medium: "#48aab7",
  high: "#126d7b",
};

export function clampMastery(value: MasteryValue): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return Math.min(1, Math.max(0, value));
}

export function getMasteryBand(value: MasteryValue): MasteryBand {
  const mastery = clampMastery(value);
  if (mastery === null) return "unknown";
  if (mastery < 0.6) return mastery < 0.3 ? "very-low" : "low";
  if (mastery < 0.85) return "medium";
  return "high";
}

export function getMasteryColor(value: MasteryValue, status = ""): string {
  return getMasteryVisual(value, status).background;
}

export function getMasteryTextColor(value: MasteryValue, status = ""): string {
  return getMasteryVisual(value, status).color;
}

export function getMasteryVisual(value: MasteryValue, status = ""): MasteryVisual {
  const normalizedStatus = status.toLowerCase();
  const mastery = clampMastery(value);
  const band = getMasteryBand(mastery);

  if (["blocked", "locked"].includes(normalizedStatus)) {
    return {
      background: "#f8fafc",
      border: "#cbd5e1",
      color: "#7a889a",
      accent: "#94a3b8",
      borderStyle: "dashed",
      opacity: 0.68,
    };
  }

  if (["learning", "active"].includes(normalizedStatus)) {
    return {
      background: "#eef6ff",
      border: "#77a7ff",
      color: "#183b66",
      accent: "#2f6bff",
      borderStyle: "solid",
      opacity: 1,
    };
  }

  if (["completed", "completed_unassessed"].includes(normalizedStatus)) {
    return {
      background: "#e8f7f6",
      border: "#65c8c0",
      color: "#17434b",
      accent: "#209c96",
      borderStyle: "solid",
      opacity: 1,
    };
  }

  if (["available", "unlearned", "not_started", "unevaluated"].includes(normalizedStatus) || band === "unknown") {
    return {
      background: "#ffffff",
      border: normalizedStatus === "recommended" ? "#2f6bff" : "#cbd5e1",
      color: "#183b66",
      accent: normalizedStatus === "recommended" ? "#2f6bff" : "#94a3b8",
      borderStyle: "solid",
      opacity: 1,
    };
  }

  const background = MASTERY_COLORS[band];
  return {
    background,
    border: normalizedStatus === "recommended" ? "#2f6bff" : background,
    color: band === "high" ? "#ffffff" : "#183b66",
    accent: normalizedStatus === "recommended" ? "#2f6bff" : background,
    borderStyle: "solid",
    opacity: 1,
  };
}

export function formatMastery(value: MasteryValue): string {
  const mastery = clampMastery(value);
  return mastery === null ? "待评估" : `${Math.round(mastery * 100)}%`;
}

export function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    completed: "已完成·待测评",
    completed_unassessed: "已完成·待测评",
    done: "已学习",
    available: "可开始",
    current: "当前推荐",
    recommended: "当前推荐",
    learning: "学习中",
    mastered: "已掌握",
    unevaluated: "待诊断",
    blocked: "先修未满足",
    locked: "尚未解锁",
  };
  return labels[status] || "待学习";
}
