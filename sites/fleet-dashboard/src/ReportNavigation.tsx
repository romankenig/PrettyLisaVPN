import { reports, type ReportPage } from "./reportRoutes";

export default function ReportNavigation({ current }: { current: ReportPage }) {
  return <nav className="report-navigation" aria-label="Отчёты PrettyLisaVPN">{reports.map(report => <a key={report.id} href={report.path} aria-current={current === report.id ? "page" : undefined}>{report.name}</a>)}</nav>;
}
