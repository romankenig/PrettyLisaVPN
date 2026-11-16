import { useLayoutEffect, useRef, useState } from "react";
import { formatDay, formatNumber } from "./analytics";
import { appPlatforms, versionSeries, type VersionReport } from "./versionUsage";
import CurrentDayNote from "./CurrentDayNote";

export default function AppVersionChart({ data, platform }: { data: VersionReport; platform: string }) {
  const [shares, setShares] = useState(false), [active, setActive] = useState<number | null>(null), [viewportWidth, setViewportWidth] = useState(0);
  const scroll = useRef<HTMLDivElement>(null), points = data.points, series = versionSeries(data, platform, shares);
  const totals = points.map(p => p.platforms === null ? null : Object.values(p.platforms[platform]?.users ?? {}).reduce((a, b) => a + b, 0));
  const maximum = shares ? 100 : Math.max(1, ...totals.map(n => n ?? 0)), width = Math.max(880, viewportWidth), slot = (width - 24) / points.length, x = (i: number) => 12 + slot * (i + .5);
  useLayoutEffect(() => { const node = scroll.current; if (!node) return; const measure = () => setViewportWidth(node.clientWidth); measure(); const observer = new ResizeObserver(measure); observer.observe(node); return () => observer.disconnect(); }, []);
  useLayoutEffect(() => { if (scroll.current) scroll.current.scrollLeft = scroll.current.scrollWidth - scroll.current.clientWidth; }, [width, data.through_date]);
  const focusDay = (i: number) => { setActive(i); if (scroll.current) scroll.current.scrollLeft = Math.max(0, x(i) - scroll.current.clientWidth / 2); };
  const today = points.at(-1)!.platforms?.[platform];
  return <section className="panel analytics-chart app-version-chart">
    <div className="section-title"><h2>Версии {appPlatforms[platform]} по дням</h2><div className="chart-switch" role="group" aria-label="Версии: единицы"><button aria-pressed={!shares} onClick={() => setShares(false)}>Количество</button><button aria-pressed={shares} onClick={() => setShares(true)}>Доли, %</button></div></div>
    <CurrentDayNote date={data.through_date} />
    <div className="analytics-legend">{series.map(row => <span key={row.name}><svg width="12" height="12" aria-hidden="true"><rect width="12" height="12" rx="2" fill={row.color} /></svg>{row.name}</span>)}</div>
    <div className="analytics-plot" role="group" tabIndex={0} aria-label="Версии приложений по дням. Стрелки — значения по дням." onFocus={() => focusDay(30)} onBlur={() => setActive(null)} onKeyDown={event => { if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); focusDay(Math.max(0, Math.min(30, (active ?? 30) + (event.key === "ArrowRight" ? 1 : -1)))); } }}>
      <div className="daily-device-plot"><svg className="device-chart-axis" width="44" height="256" aria-hidden="true">{[0, .5, 1].map(part => <text key={part} x="36" y={214 - 174 * part} textAnchor="end" className="chart-axis">{formatNumber(maximum * part)}{shares ? "%" : ""}</text>)}</svg>
        <div className="chart-scroll" ref={scroll}><svg className="chart-svg" viewBox={`0 0 ${width} 256`} style={{ width, minWidth: width }} role="img" aria-label="Пользователи версий приложений по дням" onPointerLeave={() => setActive(null)} onPointerMove={event => { const rect = event.currentTarget.getBoundingClientRect(); setActive(Math.max(0, Math.min(30, Math.floor(((event.clientX - rect.left) * width / rect.width - 12) / slot)))); }}>
          {[0, .5, 1].map(part => <line key={part} x1="0" x2={width} y1={210 - 174 * part} y2={210 - 174 * part} className="chart-grid" />)}
          {points.map((point, i) => { let bottom = 210; return <g key={point.date} data-day={point.date} data-partial={point.partial || undefined}>
            {point.partial && <rect x={x(i) - slot * .45} y="30" width={slot * .9} height="184" rx="3" fill="#f0e9fa" stroke="#5f22d9" strokeDasharray="3 3" />}
            {totals[i] === null && <line x1={x(i) - slot * .3} x2={x(i) + slot * .3} y1="210" y2="210" stroke="#9c9c9c" strokeWidth="3"><title>Нет данных</title></line>}
            {series.map(row => { const value = row.values[i]; if (value === null || value === 0) return null; const height = value / maximum * 174; bottom -= height; return <rect key={row.name} x={x(i) - slot * .36} y={bottom} width={slot * .72} height={height} fill={row.color}><title>{formatDay(point.date)} · {row.name}: {formatNumber(value)}{shares ? "%" : ""}</title></rect>; })}
            {(i % 5 === 0 || i === 30) && <text x={x(i)} y="236" textAnchor={i === 0 ? "start" : i === 30 ? "end" : "middle"} className="chart-axis">{formatDay(point.date)}</text>}
            {point.partial && <text x={x(i)} y="252" textAnchor="end" className="chart-axis">неполный день</text>}
          </g>; })}
          {active !== null && <line x1={x(active)} x2={x(active)} y1="30" y2="210" className="analytics-cursor" />}
        </svg></div></div>
      {active !== null && <div className="analytics-tooltip" role="tooltip"><strong>{formatDay(points[active].date)}{points[active].partial && " · неполный день"}</strong>{totals[active] === null ? <div>До начала сбора — нет данных</div> : <>{series.map(row => <div key={row.name}>{row.name}: <b>{formatNumber(row.values[active])}{shares && row.values[active] !== null ? "%" : ""}</b></div>)}{totals[active] === 0 && <div>Нет активности в этот день</div>}</>}</div>}
    </div>
    <h3>Активных пользователей сегодня: {points[30].platforms === null ? "нет данных" : today?.active_users ?? 0}</h3>
    <div className="service-table-wrap"><table className="service-table"><thead><tr><th>Версия</th><th>Пользователи</th><th>Доля</th><th>Устройства</th></tr></thead><tbody>{series.filter(row => today?.users[row.name]).map(row => <tr key={row.name}><td>{row.name}</td><td>{today!.users[row.name]}</td><td>{formatNumber(100 * today!.users[row.name] / totals[30]!)}%</td><td>{today!.devices[row.name]}</td></tr>)}</tbody></table></div>
    {!today && <p className="empty">{points[30].platforms === null ? "Сбор версий ещё не начат." : "Сегодня активности этой платформы пока нет."}</p>}
    <p className="metric-definition">Активность — авторизованные запросы приложения; VPN-подключение не требуется. На устройстве берётся последняя сообщённая версия за день. Пользователь учитывается один раз на версию и платформу в день; несколько устройств с одной версией не увеличивают число пользователей. Если версии на устройствах различаются, пользователь входит в каждую категорию. Доля — категория / сумма категорий за этот день. UNKNOWN — версия не сообщена в этот день. Chrome Extension учитывается отдельно от Windows. Тестовые аккаунты исключены; DEMO учитывается по гостевому аккаунту. История посещений не собирается.</p>
  </section>;
}
