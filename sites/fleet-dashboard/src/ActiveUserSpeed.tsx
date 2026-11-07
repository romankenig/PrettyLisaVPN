import { useEffect, useState } from "react";
import { date, TIME_ZONE_LABEL } from "./time";
import { speedNumber, speedSegments, speedTooltip, type SpeedHistory, type SpeedPoint } from "./activeSpeed";

type Server = { id: string; name: string; group?: string };

function DirectionChart({ history, direction }: { history: SpeedHistory; direction: "download" | "upload" }) {
  const [focus, setFocus] = useState<SpeedPoint | null>(null);
  const points = history.points;
  const maximum = Math.max(0.1, ...points.flatMap(point => [point[direction].mean_mbps ?? 0, point[direction].reference_mbps ?? 0])) * 1.1;
  const x = (index: number) => 64 + index * 866 / Math.max(1, points.length - 1);
  const y = (value: number) => 205 - value / maximum * 178;
  const tooltip = focus && speedTooltip(focus, history.bucket_seconds);
  return <div className="active-speed-direction">
    <h3>{direction === "download" ? "↓ Скачивание пользователем" : "↑ Загрузка пользователем"} <small>Мбит/с</small></h3>
    <div className="chart-scroll"><svg className="chart-svg" viewBox="0 0 960 244" role="group" aria-label={`${direction === "download" ? "Скачивание" : "Загрузка"}: фактическая средняя и ориентир проверки`}>
      {[0, 1, 2, 3, 4].map(tick => <g key={tick}><line x1="64" x2="930" y1={y(maximum * tick / 4)} y2={y(maximum * tick / 4)} className="chart-grid" /><text x="54" y={y(maximum * tick / 4) + 4} textAnchor="end" className="chart-axis">{speedNumber(maximum * tick / 4)}</text></g>)}
      {points.filter(point => point.coverage.fraction == null || point.coverage.fraction < 0.9999).map(point => { const index = points.indexOf(point); return <rect key={point.at} x={x(index) - 1} y="211" width={Math.max(2, 866 / points.length)} height="3" fill="#d7ad0d" />; })}
      {(["reference_mbps", "mean_mbps"] as const).map(metric => <g key={metric} stroke={metric === "mean_mbps" ? "#5f22d9" : "#169b91"}>
        {speedSegments(points, direction, metric).map((segment, index) => <g key={index}>
          <polyline fill="none" strokeWidth="2.4" strokeDasharray={metric === "reference_mbps" ? "5 4" : undefined} points={segment.map(item => `${x(item.index)},${y(item.value)}`).join(" ")} />
          {segment.map(item => <circle key={item.index} cx={x(item.index)} cy={y(item.value)} r={metric === "reference_mbps" ? 3.5 : 2.5} fill="white" strokeWidth="2" />)}
        </g>)}
      </g>)}
      {[0, 1, 2, 3, 4].map(tick => { const index = Math.round((points.length - 1) * tick / 4); return points[index] && <text key={tick} x={x(index)} y="237" textAnchor={tick === 0 ? "start" : tick === 4 ? "end" : "middle"} className="chart-axis">{date(points[index].at, false)}</text>; })}
      {points.map((point, index) => <rect key={point.at} x={x(index) - Math.max(3, 433 / points.length)} y="20" width={Math.max(6, 866 / points.length)} height="190" fill="transparent" tabIndex={0} role="button" className="speed-hit" aria-label={speedTooltip(point, history.bucket_seconds).join(". ")} onPointerEnter={() => setFocus(point)} onPointerLeave={() => setFocus(null)} onFocus={() => setFocus(point)} onBlur={() => setFocus(null)} onClick={() => setFocus(point)}><title>{speedTooltip(point, history.bucket_seconds).join("\n")}</title></rect>)}
    </svg></div>
    {tooltip && <div className="speed-tooltip" role="tooltip">{tooltip.map((line, index) => <div key={index}>{line}</div>)}</div>}
  </div>;
}

export default function ActiveUserSpeed({ nodes, refreshKey }: { nodes: Server[]; refreshKey: string | null }) {
  const exits = nodes.filter(node => node.group !== "INTERMEDIATE");
  const [period, setPeriod] = useState("1h");
  const [selected, setSelected] = useState<string[] | null>(null);
  const ids = exits.filter(node => selected === null || selected.includes(node.id)).map(node => node.id).sort();
  const query = new URLSearchParams({ period });
  ids.forEach(id => query.append("node_ids", id));
  const key = query.toString();
  const [result, setResult] = useState<{ key: string; data: SpeedHistory } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const data = result?.key === key ? result.data : null;
  useEffect(() => {
    const abort = new AbortController();
    if (!ids.length) return () => abort.abort();
    const refresh = async () => {
      try {
        const response = await fetch(`/dashboard/api/active-user-speed?${key}`, { cache: "no-store", signal: abort.signal });
        if (!response.ok) throw new Error("unavailable");
        const payload = await response.json() as SpeedHistory;
        if (!Array.isArray(payload.points)) throw new Error("invalid");
        if (!abort.signal.aborted) { setResult({ key, data: payload }); setError(null); }
      } catch {
        if (!abort.signal.aborted) { setResult(null); setError(key); }
      }
    };
    void refresh();
    const timer = setInterval(() => void refresh(), 60000);
    return () => { abort.abort(); clearInterval(timer); };
  }, [key, ids.length, refreshKey]);
  const available = data?.points.some(point => point.download.mean_mbps !== null || point.upload.mean_mbps !== null);
  return <section id="active-user-speed" className="panel active-speed" aria-label="Средняя скорость активного пользователя">
    <div className="section-title"><div><h2>Средняя скорость активного пользователя</h2><p>Фактическая скорость во время передачи данных. Не показывает максимальную доступную скорость соединения</p></div><div className="chart-switch" role="group" aria-label="Период скорости">{[["1h", "Последний час"], ["24h", "24 часа"], ["7d", "7 дней"]].map(([value, label]) => <button key={value} aria-pressed={period === value} onClick={() => setPeriod(value)}>{label}</button>)}</div></div>
    <fieldset className="speed-servers"><legend>Серверы выхода</legend><button onClick={() => setSelected(null)}>Выбрать все</button>{exits.map(node => <label key={node.id}><input type="checkbox" checked={ids.includes(node.id)} onChange={event => setSelected(event.target.checked ? [...ids, node.id] : ids.filter(id => id !== node.id))} />{node.name}</label>)}</fieldset>
    {!ids.length ? <div className="empty">Выберите хотя бы один сервер FREE / PREMIUM. Транзит не учитывается повторно.</div> : error === key ? <div role="alert" className="notice">Статистика скорости недоступна. Повторим запрос через минуту.</div> : !data ? <div className="empty" role="status">Получаем статистику скорости…</div> : <>
      <div className="chart-legend speed-legend"><span><i className="actual-key" />Средняя фактическая</span><span><i className="reference-key" />Измеренный ориентир пропускной способности</span><span><i className="partial-key" />Неполные данные серверов</span></div>
      {!available && <p className="notice">За этот период ещё нет подтверждённых активных интервалов. Отсутствие данных и отсутствие активности не отображаются нулевой скоростью.</p>}
      <DirectionChart key={`${key}-down`} history={data} direction="download" />
      <DirectionChart key={`${key}-up`} history={data} direction="upload" />
      <p className="history-note">Активность: строго больше {speedNumber(data.activity_threshold_bps / 1000)} Кбит/с за интервал около 5 секунд, отдельно по направлениям. Все подключения аккаунта на выбранных серверах объединены. Точка: {data.bucket_seconds / 60} мин · {TIME_ZONE_LABEL}. Наведите курсор или установите фокус на график для подробностей.</p>
      <p className="history-note">Ориентир — медиана результатов синтетических проверок выбранных серверов в том же временном блоке, а не гарантированный максимум пользователя. Редкие проверки показаны только там, где есть замер. Процент сравнивает среднюю с ориентиром при полной выборке; это не загрузка канала, он может превышать 100%. Пропуски не заполняются.</p>
    </>}
  </section>;
}
