import { useEffect, useRef, useState } from "react";
import { planFromSearch, reportPlanNames, reportTariffs, selectedPlans, togglePlan, withPlan, type ReportPlan } from "./reportPlan";

export function useReportPlan(): [ReportPlan, (value: ReportPlan) => void] {
  const [plan, setPlan] = useState<ReportPlan>(() => planFromSearch(window.location.search));
  return [plan, value => { setPlan(value); window.history.replaceState(null, "", withPlan(window.location.pathname + window.location.search, value) + window.location.hash); }];
}
export default function PlanFilter({ plan, onChange, note }: { plan: ReportPlan; onChange: (value: ReportPlan) => void; note: string }) {
  const selected = selectedPlans(plan), all = useRef<HTMLInputElement>(null);
  useEffect(() => { if (all.current) all.current.indeterminate = selected.length > 0 && selected.length < reportTariffs.length; }, [plan]);
  return <div className="report-plan-filter">
    <fieldset className="report-plan-options"><legend>Тариф пользователя</legend>
      <label><input ref={all} type="checkbox" checked={plan === "ALL"} onChange={event => onChange(event.target.checked ? "ALL" : "NONE")} />Все тарифы</label>
      {reportTariffs.map(value => <label key={value}><input type="checkbox" checked={selected.includes(value)} onChange={event => onChange(togglePlan(plan, value, event.target.checked))} />{reportPlanNames[value]}</label>)}
    </fieldset>
    <p>{note}</p>
    {plan === "NONE" && <p className="report-plan-empty" role="status">Тарифы не выбраны. Отметьте один или несколько тарифов, чтобы увидеть пользовательскую статистику.</p>}
  </div>;
}
