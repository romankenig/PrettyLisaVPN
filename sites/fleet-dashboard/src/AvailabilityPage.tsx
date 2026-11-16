import { useEffect } from "react";
import { LockKeyhole } from "lucide-react";
import MethodAvailability from "./MethodAvailability";
import ServiceAvailability from "./ServiceAvailability";
import ReportNavigation from "./ReportNavigation";

export default function AvailabilityPage({ kind }: { kind: "methods" | "services" }) {
  const title = kind === "methods" ? "Стабильность способов подключения" : "Стабильность сервисов";
  useEffect(() => { document.title = `PrettyLisaVPN — ${title}`; }, [title]);
  return <>
    <header className="topbar"><a href="/dashboard/"><img src="/dashboard/logo.svg" alt="PrettyLisaVPN" width={236} height={54} /></a><div className="private"><LockKeyhole size={14} />Приватный мониторинг</div></header>
    <main className="workspace"><ReportNavigation current={kind} />
      <div className="heading"><div><div className="eyebrow">Доступность / {kind === "methods" ? "Способы подключения" : "Сервисы"}</div><h1>{title}</h1><p>Ежедневные проверки и распределение сессий по дням · GMT+3</p></div></div>
      {kind === "methods" ? <MethodAvailability /> : <ServiceAvailability />}
    </main>
  </>;
}
