import PlanFilter, { useReportPlan } from "./PlanFilter";
import { useEffect } from "react";
import { LockKeyhole } from "lucide-react";
import MethodAvailability from "./MethodAvailability";
import ServiceAvailability from "./ServiceAvailability";
import ReportNavigation from "./ReportNavigation";

export default function AvailabilityPage({ kind }: { kind: "methods" | "services" }) {
  const [plan, setPlan] = useReportPlan();
  const title = kind === "methods" ? "Стабильность способов подключения" : "Стабильность сервисов";
  useEffect(() => { document.title = `PrettyLisaVPN — ${title}`; }, [title]);
  return <>
    <header className="topbar"><a href="/dashboard/"><img src="/dashboard/logo.svg" alt="PrettyLisaVPN" width={236} height={54} /></a><div className="private"><LockKeyhole size={14} />Приватный мониторинг</div></header>
    <main className="workspace"><ReportNavigation current={kind} plan={plan} />
      <div className="heading"><div><div className="eyebrow">Доступность / {kind === "methods" ? "Способы подключения" : "Сервисы"}</div><h1>{title}</h1><p>Ежедневные проверки и распределение сессий по дням · GMT+3</p></div></div>
      <PlanFilter plan={plan} onChange={setPlan} note="Фильтр применяется к пользовательским подключениям по тарифу при создании сессии. Синтетические проверки доступности общие для всех тарифов." />
      {kind === "methods" ? <MethodAvailability plan={plan} /> : <ServiceAvailability plan={plan} />}
    </main>
  </>;
}
