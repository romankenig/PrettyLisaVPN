import { useEffect, useRef } from "react";
import { date, TIME_ZONE_LABEL } from "./time";
import { hourMeasurements, type FocusedHour } from "./history";

const metric = (value: number | null, digits = 1) => value == null ? "—" : new Intl.NumberFormat("ru-RU", { maximumFractionDigits: digits }).format(value);
const statuses: Record<string, string> = { HEALTHY: "Доступен", DEGRADED: "С ограничениями", FAILED: "Сбой", UNKNOWN: "Нет подтверждения" };

export default function HourDetails({ focus, nodes }: { focus: FocusedHour; nodes: Parameters<typeof hourMeasurements>[0] }) {
  const rows = hourMeasurements(nodes, focus);
  const section = useRef<HTMLElement>(null);
  useEffect(() => { section.current?.focus({ preventScroll: true }); section.current?.scrollIntoView({ block: "nearest" }); }, [focus]);
  return <section ref={section} tabIndex={-1} className="panel hour-measurements" aria-label="Результаты выбранного часа">
    <div className="section-title"><div><h2>Проверки: {date(focus.at)} {TIME_ZONE_LABEL}</h2><p>Скорость и рейтинг на момент каждой проверки.</p></div></div>
    {rows.length ? <><div className="table-scroll"><table><thead><tr><th>Время, {TIME_ZONE_LABEL}</th><th>Сервер</th><th>Скорость ↓ / ↑, Мбит/с</th><th>Рейтинг / 100</th><th>Активных</th><th>Результат</th></tr></thead><tbody>{rows.map((row, index) => <tr key={`${row.nodeId}-${row.observed_at}-${index}`}><td>{date(row.observed_at)}</td><td>{row.nodeName}</td><td>{metric(row.download_mbps)} / {metric(row.upload_mbps)}</td><td>{metric(row.quality, 0)}</td><td>{metric(row.active_connections, 0)}</td><td>{statuses[row.status] ?? row.status}</td></tr>)}</tbody></table></div><p className="history-note">«—» означает, что значение не измерялось или ещё не сохранялось. Старые рейтинги не восстанавливаются задним числом.</p></> : <p className="history-note">За выбранный час сохранённых замеров нет.</p>}
  </section>;
}
