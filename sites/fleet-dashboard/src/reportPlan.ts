export const reportPlans = ["ALL", "DEMO", "FREE", "PREMIUM", "PLATINUM", "UNKNOWN"] as const;
export type ReportPlan = typeof reportPlans[number];
export const reportPlanNames: Record<ReportPlan, string> = { ALL: "Все тарифы", DEMO: "DEMO", FREE: "Free", PREMIUM: "Premium", PLATINUM: "Platinum", UNKNOWN: "Неизвестен" };
export function planFromSearch(search: string): ReportPlan {
  const value = new URLSearchParams(search).get("plan");
  return reportPlans.includes(value as ReportPlan) ? value as ReportPlan : "ALL";
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
