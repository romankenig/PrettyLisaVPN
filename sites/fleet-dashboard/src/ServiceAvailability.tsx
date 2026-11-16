import { useEffect, useState } from "react";
import AnalyticsChart from "./AnalyticsChart";
import DailySelectionDistribution from "./DailySelectionDistribution";
import { readSelectionHistory, type SelectionHistory } from "./selectionHistory";
import { formatNumber } from "./analytics";
import { date } from "./time";

type Service = { id: string; name: string; points: {date: string; score: number | null}[]; week_score: number | null; observed_days: number; today_score: number | null; today_code: string | null; next_check_at: string };
type Report = { generated_at: string; services: Service[]; selection_history?: SelectionHistory; selection: { active_sessions: number; observed_sessions: number; unknown_mode_sessions: number; items: {name: string; count: number}[] } };

export default function ServiceAvailability() {
  const [data, setData] = useState<Report | null>(null);
  const [error, setError] = useState(false);
  const [selected, setSelected] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    const refresh = async () => {
      try {
        const response = await fetch("/dashboard/api/services", { signal: controller.signal, cache: "no-store" });
        if (!response.ok) throw new Error("Unavailable");
        const report = await response.json() as Report;
        if (!Array.isArray(report.services) || !report.selection) throw new Error("Invalid");
        if (report.selection_history !== undefined) readSelectionHistory(report.selection_history);
        if (!controller.signal.aborted) { setData(report); setError(false); }
      } catch { if (!controller.signal.aborted) setError(true); }
    };
    void refresh(); const timer = setInterval(() => void refresh(), 60000);
    return () => { controller.abort(); clearInterval(timer); };
  }, []);
  const active = data?.services.find(row => row.id === selected) ?? data?.services[0];
  return <div className="service-analytics">
    <section className="panel analytics-chart"><div className="section-title"><div><h2>Доступность выбранных сервисов</h2><p>Семь завершённых дней · GMT+3 · независимая проверка каждого сервиса раз в день</p></div><select aria-label="Сервис для графика" value={active?.id ?? ""} onChange={event => setSelected(event.target.value)}>{data?.services.map(service => <option key={service.id} value={service.id}>{service.name}</option>)}</select></div>
      {error && <p role="alert" className="notice">Не удалось обновить данные сервисов. {data && "Показан предыдущий результат."}</p>}
      {!data && !error && <p role="status">Загружаем результаты проверок…</p>}
      {data && <div className="service-table-wrap"><table className="service-table"><thead><tr><th>Сервис</th><th>Среднее за неделю</th><th>Дней с данными</th><th>Сегодня</th><th>Следующая проверка</th></tr></thead><tbody>{data.services.map(service => <tr key={service.id}><td><button onClick={() => setSelected(service.id)}>{service.name}</button></td><td>{formatNumber(service.week_score)}{service.week_score !== null && "%"}</td><td>{service.observed_days} / 7</td><td title={service.today_code ?? "PENDING"}>{service.today_score === null ? "Ожидаем данные" : `${formatNumber(service.today_score)}%`}</td><td>{date(service.next_check_at)}</td></tr>)}</tbody></table></div>}
      <p className="metric-definition">Случайная существующая публичная ссылка, сервер и тип подключения. Сразу успешно — 100%; затем оценка уменьшается пропорционально минутам до первого успеха. Без успеха за 30 минут или после перебора вариантов — 0%. Отсутствие проверяемой ссылки или измерений — пропуск. Первая серия запускается после включения; прошедшие дни не заполняются искусственно.</p>
    </section>
    {active && <AnalyticsChart title={`Доступность · ${active.name}`} dates={active.points.map(point => point.date)} unit="%" series={[{ name: active.name, color: "#5f22d9", values: active.points.map(point => point.score) }]} explanation={`Среднее считается только по дням с результатом: ${active.observed_days} из 7. Текущий день показан отдельно в таблице.`} />}
    <DailySelectionDistribution title="Выбранные сервисы по дням" history={data?.selection_history} explanation="Одна отметка на выбранный сервис в сессии или попытке с режимом «защита выбранного трафика». Результат относится к VPN-подключению, а не к доступности сервиса. UNKNOWN объединяет ручные правила и неизвестные ID; конкретные правила остаются только в БД. Это выбранные правила, а не история посещений." />
  </div>;
}
