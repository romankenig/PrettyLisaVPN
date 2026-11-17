import { withPlan, type ReportPlan } from "./reportPlan";
import { reports, type ReportPage } from "./reportRoutes";

export default function ReportNavigation({ current, plan = "ALL" }: { current: ReportPage; plan?: ReportPlan }) {
  return <nav className="report-navigation" aria-label="Отчёты PrettyLisaVPN">{reports.map(report => <a key={report.id} href={withPlan(report.path, plan)} aria-current={current === report.id ? "page" : undefined}>{report.name}</a>)}</nav>;
}
