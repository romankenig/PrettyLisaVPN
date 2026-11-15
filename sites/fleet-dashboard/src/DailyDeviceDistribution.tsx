import { useLayoutEffect, useRef, useState } from "react";
import { formatDay, formatNumber, type AnalyticsPoint, type CurrentDevicePoint } from "./analytics";
import { deviceChartPoints, deviceSeries, deviceTotal, type DeviceMeasure } from "./deviceDistribution";
import { date } from "./time";

export default function DailyDeviceDistribution({ points: history, today }: { points: AnalyticsPoint[]; today?: CurrentDevicePoint }) {
  const points = deviceChartPoints(history, today);
  const [measure, setMeasure] = useState<DeviceMeasure>("users");
  const [shares, setShares] = useState(false);
  const [active, setActive] = useState<number | null>(null);
  const [viewportWidth, setViewportWidth] = useState(0);
  const scroll = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const node = scroll.current;
    if (!node) return;
    const measure = () => setViewportWidth(node.clientWidth);
    measure(); const observer = new ResizeObserver(measure); observer.observe(node);
    return () => observer.disconnect();
  }, []);
  const series = deviceSeries(points, measure, shares);
  const totals = points.map(point => deviceTotal(point, measure));
  const maximum = shares ? 100 : Math.max(1, ...totals.map(total => total ?? 0));
  const width = Math.max(760, points.length * 20 + 24, viewportWidth), slot = (width - 24) / Math.max(1, points.length);
  const x = (i: number) => 12 + slot * (i + .5);
  useLayoutEffect(() => {
    const node = scroll.current;
    if (node) node.scrollLeft = node.scrollWidth - node.clientWidth;
  }, [width]);
  const focusDay = (i: number) => {
    setActive(i);
    if (scroll.current) scroll.current.scrollLeft = Math.max(0, x(i) - scroll.current.clientWidth / 2);
  };
  return <section className="panel analytics-chart daily-device-chart">
    <div className="section-title"><h2>С каких устройств подключались</h2><div className="device-chart-controls">
      <div className="chart-switch" role="group" aria-label="Устройства: что считать"><button aria-pressed={measure === "users"} onClick={() => setMeasure("users")}>Юзеры</button><button aria-pressed={measure === "connections"} onClick={() => setMeasure("connections")}>Подключения</button></div>
      <div className="chart-switch" role="group" aria-label="Устройства: единицы"><button aria-pressed={!shares} onClick={() => setShares(false)}>Количество</button><button aria-pressed={shares} onClick={() => setShares(true)}>Доли, %</button></div>
    </div></div>
    {today && <p className="device-current-day"><strong>{formatDay(today.date)} · неполный день</strong><span>Обновлено {date(today.updated_at)} GMT+3 · обновление раз в минуту</span></p>}
    <div className="analytics-legend">{series.map(row => <span key={row.name}><svg width="12" height="12" aria-hidden="true"><rect width="12" height="12" rx="2" fill={row.color}/></svg>{row.name}</span>)}</div>
    <div className="analytics-plot" role="group" tabIndex={0} aria-label="Устройства по дням. Стрелки влево и вправо — значения по дням."
      onFocus={() => focusDay(points.length - 1)} onBlur={() => setActive(null)}
      onKeyDown={event => { if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); focusDay(Math.max(0, Math.min(points.length - 1, (active ?? points.length - 1) + (event.key === "ArrowRight" ? 1 : -1)))); } }}>
      <div className="daily-device-plot"><svg className="device-chart-axis" width="44" height="256" aria-hidden="true">{[0, .5, 1].map(part => <text key={part} x="36" y={214 - 174 * part} textAnchor="end" className="chart-axis">{formatNumber(maximum * part)}{shares ? "%" : ""}</text>)}</svg>
      <div className="chart-scroll" ref={scroll}><svg className="chart-svg" viewBox={`0 0 ${width} 256`} style={{ width, minWidth: width }} role="img" aria-label={`Распределение по дням: ${measure === "users" ? "юзеры" : "подключения"}, ${shares ? "доли" : "количество"}`}
        onPointerLeave={() => setActive(null)} onPointerMove={event => {
          const rect = event.currentTarget.getBoundingClientRect();
          setActive(Math.max(0, Math.min(points.length - 1, Math.floor(((event.clientX - rect.left) * width / rect.width - 12) / slot))));
        }}>
        {[0, .5, 1].map(part => <line key={part} x1="0" x2={width} y1={210 - 174 * part} y2={210 - 174 * part} className="chart-grid"/>)}
        {points.map((point, i) => { let bottom = 210; return <g key={point.date} data-partial={point.partial || undefined}>
          {point.partial && <rect x={x(i) - slot * .45} y="30" width={slot * .9} height="184" rx="3" fill="#f0e9fa" stroke="#5f22d9" strokeDasharray="3 3"><title>{formatDay(point.date)} · неполный день</title></rect>}
          {totals[i] === null && <line x1={x(i) - slot * .25} x2={x(i) + slot * .25} y1="210" y2="210" stroke="#9c9c9c" strokeWidth="3"><title>{formatDay(point.date)}: нет данных</title></line>}
          {series.map(row => { const value = row.values[i]; if (value === null || value === 0) return null; const height = value / maximum * 174; bottom -= height; return <rect key={row.name} x={x(i) - slot * .36} y={bottom} width={slot * .72} height={height} fill={row.color}><title>{formatDay(point.date)}{point.partial ? " · неполный день" : ""} · {row.name}: {formatNumber(value)}{shares ? "%" : ""}</title></rect>; })}
          {(i % Math.max(1, Math.ceil(points.length / 7)) === 0 || i === points.length - 1) && <text x={x(i)} y="236" textAnchor={i === 0 ? "start" : i === points.length - 1 ? "end" : "middle"} className="chart-axis">{formatDay(point.date)}</text>}
          {point.partial && <text x={x(i)} y="252" textAnchor="end" className="chart-axis">неполный день</text>}
        </g>; })}
        {active !== null && <line x1={x(active)} x2={x(active)} y1="30" y2="210" className="analytics-cursor"/>}
      </svg></div></div>
      {active !== null && points[active] && <div className="analytics-tooltip" role="tooltip"><strong>{formatDay(points[active].date)} {points[active].date.slice(0, 4)}{points[active].partial && " · неполный день"}</strong>{totals[active] === null ? "Нет данных" : <>{series.map(row => <div key={row.name}>{row.name}: <b>{formatNumber(row.values[active])}{shares && row.values[active] !== null ? "%" : ""}</b></div>)}{totals[active] === 0 && <div>Нет подключений в этот день</div>}</>}</div>}
    </div>
    {!totals.some(total => total !== null) && <p className="empty">Пока нет ежедневных данных по устройствам.</p>}
    <p className="metric-definition">Каждый столбец — календарный день, GMT+3; текущий день помечен как неполный. Цвет — платформа устройства, Chrome Extension учитывается отдельно от Windows. Юзеры — уникальные аккаунты с подтверждённым подключением, один раз за день на каждой платформе. Повторные подключения считаются отдельно в режиме «Подключения». Один аккаунт на нескольких платформах входит в каждую категорию; доля — категория / сумма категорий за этот день. Тестовые аккаунты исключены; отсутствие истории не заменяется нулём.</p>
  </section>;
}
