import { useEffect, useState } from "react";
import AnalyticsChart from "./AnalyticsChart";
import BarDistribution from "./BarDistribution";
import { formatNumber } from "./analytics";
import { methodName, readMethodReport, type MethodReport } from "./connectionMethods";
import { date } from "./time";

export default function MethodAvailability() {
  const [data, setData] = useState<MethodReport | null>(null);
  const [error, setError] = useState(false);
  const [selected, setSelected] = useState("wireguard");
  useEffect(() => {
    const controller = new AbortController();
    const refresh = async () => {
      try {
        const response = await fetch("/dashboard/api/connection-methods", { signal: controller.signal, cache: "no-store" });
        if (!response.ok) throw new Error("Unavailable");
        const report = readMethodReport(await response.json());
        if (!controller.signal.aborted) { setData(report); setError(false); }
      } catch { if (!controller.signal.aborted) setError(true); }
    };
    void refresh(); const timer = setInterval(() => void refresh(), 60000);
    return () => { controller.abort(); clearInterval(timer); };
  }, []);
  const active = data?.methods.find(row => row.id === selected) ?? data?.methods[0];
  return <div className="service-analytics">
    <section className="panel analytics-chart"><div className="section-title"><div><h2>Доступность способов подключения</h2><p>Семь завершённых дней · GMT+3 · проверка каждого способа раз в день</p></div><select aria-label="Способ подключения для графика" value={active?.id ?? ""} onChange={event => setSelected(event.target.value)}>{data?.methods.map(method => <option key={method.id} value={method.id}>{methodName(method.id)}</option>)}</select></div>
      {error && <p role="alert" className="notice">Не удалось обновить статистику способов подключения. {data && "Показан предыдущий результат."}</p>}
      {!data && !error && <p role="status">Загружаем результаты проверок…</p>}
      {data && <div className="service-table-wrap"><table className="service-table"><thead><tr><th>Способ подключения</th><th>Среднее за неделю</th><th>Дней с данными</th><th>Сегодня</th><th>Следующая проверка</th></tr></thead><tbody>{data.methods.map(method => <tr key={method.id}><td><button onClick={() => setSelected(method.id)}>{methodName(method.id)}</button></td><td>{formatNumber(method.week_score)}{method.week_score !== null && "%"}</td><td>{method.observed_days} / 7</td><td title={method.today_code ?? "PENDING"}>{method.today_score === null ? "Ожидаем данные" : `${formatNumber(method.today_score)}%`}</td><td>{date(method.next_check_at)}</td></tr>)}</tbody></table></div>}
      <p className="metric-definition">Способ фиксирован, сервер и существующая публичная ссылка из каталога выбираются случайно; «+» проверяется через промежуточный сервер. При неудаче — новый маршрут не чаще раза в минуту. Сразу успешно — 100%; далее оценка = 100 × (1 − минуты до успешной попытки / 30). Без успеха за 30 минут или после перебора маршрутов — 0%; без измерений — пропуск. Проверки распределены по дню, первая серия — после запуска. Это оценка времени до успеха из VPN-узлов, а не доля успешных пользовательских подключений.</p>
    </section>
    {active && <AnalyticsChart title={`Доступность · ${methodName(active.id)}`} dates={active.points.map(point => point.date)} unit="%" series={[{ name: methodName(active.id), color: "#5f22d9", values: active.points.map(point => point.score) }]} explanation={`Среднее по дням с результатом: ${active.observed_days} из 7. Сегодня показано отдельно; прошлые пропуски не восстанавливаются.`} />}
    <BarDistribution title="Способы подключения в открытых сессиях" items={(data?.selection.items ?? []).map(row => ({ name: methodName(row.method), count: row.count }))} explanation={`Одна подтверждённая открытая сессия — одна отметка. Доля — сессии способа / все открытые сессии; все режимы трафика. Всего: ${data?.selection.active_sessions ?? 0}. Обычные и «+» способы учитываются отдельно. Тестовые аккаунты исключены.`} />
  </div>;
}
