import { useState } from "react";
import { planFromSearch, reportPlanNames, reportPlans, withPlan, type ReportPlan } from "./reportPlan";

export function useReportPlan(): [ReportPlan, (value: ReportPlan) => void] {
  const [plan, setPlan] = useState<ReportPlan>(() => planFromSearch(window.location.search));
  return [plan, value => { setPlan(value); window.history.replaceState(null, "", withPlan(window.location.pathname + window.location.search, value) + window.location.hash); }];
}
export default function PlanFilter({ plan, onChange, note }: { plan: ReportPlan; onChange: (value: ReportPlan) => void; note: string }) {
  return <div className="report-plan-filter"><label className="select">Тариф пользователя <select aria-label="Тариф пользователя" value={plan} onChange={event => onChange(event.target.value as ReportPlan)}>{reportPlans.map(value => <option value={value} key={value}>{reportPlanNames[value]}</option>)}</select></label><p>{note}</p></div>;
}
