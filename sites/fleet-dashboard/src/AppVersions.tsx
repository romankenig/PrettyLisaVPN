import { validateReportPlan, withPlan } from "./reportPlan";
import { useEffect, useState } from "react";
import PlanFilter, { useReportPlan } from "./PlanFilter";
import ReportNavigation from "./ReportNavigation";
import AppVersionChart from "./AppVersionChart";
import { appPlatforms, readVersionReport, type VersionReport } from "./versionUsage";
import { LockKeyhole } from "lucide-react";
import { date } from "./time";

export default function AppVersions() {
  const [plan, setPlan] = useReportPlan();
  const [result, setData] = useState<VersionReport | null>(null), [error, setError] = useState(false), [platform, setPlatform] = useState("ANDROID");
  const data = (result?.plan ?? "ALL") === plan ? result : null;
  useEffect(() => {
    const controller = new AbortController();
    const refresh = async () => { try { const response = await fetch(withPlan("/dashboard/api/app-versions", plan), { signal: controller.signal, cache: "no-store" }); if (!response.ok) throw new Error("Unavailable"); const report = readVersionReport(await response.json()); validateReportPlan(report, plan); if (!controller.signal.aborted) { setData(report); setError(false); } } catch { if (!controller.signal.aborted) setError(true); } };
    void refresh(); const timer = setInterval(() => void refresh(), 60000); return () => { controller.abort(); clearInterval(timer); };
  }, [plan]);
  return <><header className="topbar"><a href="/dashboard/"><img src="/dashboard/logo.svg" alt="PrettyLisaVPN" width={236} height={54} /></a><div className="private"><LockKeyhole size={14} />Приватная аналитика</div></header><main className="workspace product-analytics"><ReportNavigation current="versions" plan={plan} /><PlanFilter plan={plan} onChange={setPlan} note="Тариф на момент последней активности устройства за день. История без сохранённого тарифа — «Неизвестен»." /><h1>Версии приложений</h1><p>Какими версиями пользуются активные пользователи · GMT+3</p>
    <section className="panel analytics-chart"><div className="section-title version-filter"><h2>Активность по версиям</h2><label className="select">Платформа <select aria-label="Платформа приложения" value={platform} onChange={event => setPlatform(event.target.value)}>{Object.entries(appPlatforms).map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label></div>
      <p>30 предыдущих дней и текущий неполный день · обновление раз в минуту</p>
      {data && <p className="muted">Обновлено {date(data.generated_at)} GMT+3. {data.collection_started_at ? `Сбор начат ${date(data.collection_started_at)} GMT+3; первый день содержит данные с этого момента.` : "Сбор ещё не начат."} Данные до начала сбора не восстанавливаются.</p>}
      {error && <p role="alert" className="notice">Не удалось обновить версии приложений. {data && "Показан предыдущий результат."}</p>}
      {!data && !error && <p role="status">Загружаем статистику версий…</p>}
    </section>{data && <AppVersionChart data={data} platform={platform} />}
  </main></>;
}
