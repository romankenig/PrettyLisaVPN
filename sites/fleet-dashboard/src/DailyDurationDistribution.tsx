import { useLayoutEffect, useRef, useState } from "react";
import { formatDay, formatNumber } from "./analytics";
import { durationSeries, unobserved, type DurationHistory, type DurationKind } from "./durationHistory";
import { date } from "./time";

export default function DailyDurationDistribution({ data, kind }: { data?: DurationHistory; kind: DurationKind }) {
  const title = kind === "session_duration" ? "Длительность подключения по дням" : "Время до первой тишины по дням";
  const [shares, setShares] = useState(false), [active, setActive] = useState<number | null>(null), [viewportWidth, setViewportWidth] = useState(0);
  const scroll = useRef<HTMLDivElement>(null);
  const points = data?.points ?? [], series = data ? durationSeries(data, kind, shares) : [], today = points.at(-1);
  const maximum = shares ? 100 : Math.max(1, ...points.map(p => p[kind]?.samples ?? 0));
  const width = Math.max(880, points.length * 22 + 24, viewportWidth), slot = (width - 24) / Math.max(1, points.length), x = (i: number) => 12 + slot * (i + .5);
  useLayoutEffect(() => {
    const node = scroll.current; if (!node) return;
    const measure = () => setViewportWidth(node.clientWidth); measure();
    const observer = new ResizeObserver(measure); observer.observe(node); return () => observer.disconnect();
  }, []);
  useLayoutEffect(() => { if (scroll.current) scroll.current.scrollLeft = scroll.current.scrollWidth - scroll.current.clientWidth; }, [width, today?.date]);
  const focus = (i: number) => { setActive(i); if (scroll.current) scroll.current.scrollLeft = Math.max(0, x(i) - scroll.current.clientWidth / 2); };
  return <section className="panel analytics-chart daily-duration-chart">
    <div className="section-title"><h2>{title}</h2><div className="chart-switch" role="group" aria-label={`${title}: единицы`}><button aria-pressed={!shares} onClick={() => setShares(false)}>Количество</button><button aria-pressed={shares} onClick={() => setShares(true)}>Доли, %</button></div></div>
    {today && <p className="device-current-day"><strong>{formatDay(today.date)} · неполный день</strong><span>Обновление раз в минуту</span></p>}
    <div className="analytics-legend">{series.map(row => <span key={row.name}><svg width="12" height="12" aria-hidden="true"><rect width="12" height="12" rx="2" fill={row.color}/></svg>{row.name}</span>)}</div>
    <div className="analytics-plot" role="group" tabIndex={0} aria-label={`${title}. Стрелки влево и вправо — значения по дням.`} onFocus={() => points.length && focus(points.length - 1)} onBlur={() => setActive(null)} onKeyDown={event => { if (points.length && (event.key === "ArrowLeft" || event.key === "ArrowRight")) { event.preventDefault(); focus(Math.max(0, Math.min(points.length - 1, (active ?? points.length - 1) + (event.key === "ArrowRight" ? 1 : -1)))); } }}>
      <div className="daily-device-plot"><svg className="device-chart-axis" width="44" height="256" aria-hidden="true">{[0, .5, 1].map(part => <text key={part} x="36" y={214 - 174 * part} textAnchor="end" className="chart-axis">{formatNumber(maximum * part)}{shares ? "%" : ""}</text>)}</svg><div className="chart-scroll" ref={scroll}><svg className="chart-svg" viewBox={`0 0 ${width} 256`} style={{ width, minWidth: width }} role="img" aria-label={`${title}: ${shares ? "доли" : "количество"}`} onPointerLeave={() => setActive(null)} onPointerMove={event => { const rect = event.currentTarget.getBoundingClientRect(); setActive(Math.max(0, Math.min(points.length - 1, Math.floor(((event.clientX - rect.left) * width / rect.width - 12) / slot)))); }}>
        {[0, .5, 1].map(part => <line key={part} x1="0" x2={width} y1={210 - 174 * part} y2={210 - 174 * part} className="chart-grid"/>)}
        {points.map((point,i) => { let bottom = 210; const missing = unobserved(point, kind); return <g key={point.date} data-date={point.date} data-partial={point.partial || undefined}>
          {point.partial && <rect x={x(i)-slot*.45} y="30" width={slot*.9} height="184" rx="3" fill="#f0e9fa" stroke="#5f22d9" strokeDasharray="3 3"/>}
          {(point[kind] === null || (!point[kind]!.samples && (missing ?? 0)>0)) && <line x1={x(i)-slot*.25} x2={x(i)+slot*.25} y1="210" y2="210" stroke="#9c9c9c" strokeWidth="3"/>}
          {series.map(row => { const value = row.values[i]; if (value === null || value === 0) return null; const height = value / maximum * 174; bottom -= height; return <rect key={row.name} x={x(i)-slot*.36} y={bottom} width={slot*.72} height={height} fill={row.color}><title>{formatDay(point.date)} · {row.name}: {formatNumber(value)}{shares ? "%" : ""}</title></rect>; })}
          {(missing ?? 0)>0 && (point[kind]?.samples ?? 0)>0 && <rect x={x(i)-slot*.4} y={bottom-2} width={slot*.8} height={212-bottom} fill="none" stroke="#9c9c9c" strokeDasharray="3 3"/>}
          {(i % Math.max(1, Math.ceil(points.length/8)) === 0 || i === points.length-1) && <text x={x(i)} y="236" textAnchor={i===0 ? "start" : i===points.length-1 ? "end" : "middle"} className="chart-axis">{formatDay(point.date)}</text>}
          {point.partial && <text x={x(i)} y="252" textAnchor="end" className="chart-axis">неполный день</text>}
        </g>; })}
      </svg></div></div>
      {active !== null && points[active] && <div className="analytics-tooltip" role="tooltip"><strong>{formatDay(points[active].date)}{points[active].partial && " · неполный день"}</strong>{points[active].sessions === null ? <div>Нет истории</div> : <>{series.map(row => <div key={row.name}>{row.name}: <b>{formatNumber(row.values[active])}{shares && row.values[active] !== null ? "%" : ""}</b></div>)}<div>Наблюдений: {formatNumber(points[active][kind]?.samples)} / {formatNumber(points[active].sessions)}</div><div>Без конечного наблюдения: {formatNumber(unobserved(points[active],kind))}</div></>}</div>}
    </div>
    {!data && <p className="empty">Ежедневное распределение пока недоступно.</p>}
    {data && <p className="muted">Обновлено {date(data.generated_at)} GMT+3</p>}
    <p className="metric-definition">Каждый столбец — день подтверждения подключения, GMT+3. Сессия учитывается один раз; позднее завершение обновляет её исходный день. {kind === "session_duration" ? "От подключения до отключения." : "От подключения до начала первых 10 секунд без изменения счётчиков байтов. Пропуски измерений не считаются тишиной."} Цвет — интервал длительности, верхняя граница включена. Доли — среди подтверждённых наблюдений внутри дня. Пунктир — часть сессий ещё без конечного наблюдения; пропуски истории не заменяются нулём. Тестовые аккаунты исключены.</p>
  </section>;
}
