export const reportTariffs = ["DEMO", "FREE", "PREMIUM", "PLATINUM", "UNKNOWN"] as const;
export type ReportTariff = typeof reportTariffs[number];
export type ReportPlan = "ALL" | "NONE" | ReportTariff | `${ReportTariff},${string}`;
export const reportPlans = ["ALL", ...reportTariffs] as const;
export const reportPlanNames: Record<typeof reportPlans[number], string> = { ALL: "Все тарифы", DEMO: "DEMO", FREE: "Free", PREMIUM: "Premium", PLATINUM: "Platinum", UNKNOWN: "Неизвестен" };

export function selectedPlans(plan: ReportPlan): readonly ReportTariff[] {
  return plan === "ALL" ? reportTariffs : plan === "NONE" ? [] : plan.split(",") as ReportTariff[];
}
export function selectionKey(values: readonly ReportTariff[]): ReportPlan {
  const ordered = reportTariffs.filter(value => values.includes(value));
  return ordered.length === reportTariffs.length ? "ALL" : (ordered.join(",") || "NONE") as ReportPlan;
}
export function parseReportPlan(value: string): ReportPlan | null {
  if (value === "ALL" || value === "NONE") return value;
  const values = value.split(",");
  return values.every(item => reportTariffs.includes(item as ReportTariff)) ? selectionKey(values as ReportTariff[]) : null;
}
export function togglePlan(plan: ReportPlan, tariff: ReportTariff, checked: boolean): ReportPlan {
  const selected = selectedPlans(plan);
  return selectionKey(checked ? [...selected, tariff] : selected.filter(value => value !== tariff));
}
export function planFromSearch(search: string): ReportPlan {
  const values = new URLSearchParams(search).getAll("plan");
  return values.length ? parseReportPlan(values.join(",")) ?? "ALL" : "ALL";
}
export function withPlan(path: string, plan: ReportPlan): string {
  const [base, search = ""] = path.split("?");
  const query = new URLSearchParams(search);
  if (plan === "ALL") query.delete("plan"); else query.set("plan", plan);
  return base + (query.size ? `?${query}` : "");
}
export function validateReportPlan(value: { plan?: string }, plan: ReportPlan) {
  if ((value.plan ?? "ALL") !== plan) throw new Error("Wrong report tariff");
}
