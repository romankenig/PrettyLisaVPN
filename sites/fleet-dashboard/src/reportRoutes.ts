export const reports = [
  { id: "servers", path: "/dashboard/", name: "Серверы" },
  { id: "methods", path: "/dashboard/connection-methods", name: "Способы подключения" },
  { id: "services", path: "/dashboard/services", name: "Сервисы" },
  { id: "product", path: "/dashboard/product-analytics", name: "Продуктовая аналитика" },
  { id: "versions", path: "/dashboard/app-versions", name: "Версии приложений" },
] as const;
export type ReportPage = typeof reports[number]["id"];
export function reportPage(path: string): ReportPage {
  return reports.find(report => report.path.replace(/\/$/, "") === path.replace(/\/$/, ""))?.id ?? "servers";
}
