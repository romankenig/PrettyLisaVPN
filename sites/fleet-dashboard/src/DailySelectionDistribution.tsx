import { useLayoutEffect, useRef, useState } from "react";
import { formatDay, formatNumber } from "./analytics";
import CurrentDayNote from "./CurrentDayNote";
import { connectionOutcomes, historyForOutcome, outcomeLabels, selectionSeries, type ConnectionOutcome, type SelectionHistory } from "./selectionHistory";
import { date } from "./time";

export default function DailySelectionDistribution({ title, history: source, explanation, name = (_, label) => label }: { title: string; history?: SelectionHistory; explanation: string; name?: (id: string, label: string) => string }) {
  const [outcome, setOutcome] = useState<ConnectionOutcome>("successful");
  const history = historyForOutcome(source, outcome);
  const [shares, setShares] = useState(false);
  const [active, setActive] = useState<number | null>(null);
  const [viewportWidth, setViewportWidth] = useState(0);
  const scroll = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const node = scroll.current; if (!node) return;
    const measure = () => setViewportWidth(node.clientWidth);
    measure(); const observer = new ResizeObserver(measure); observer.observe(node);
    return () => observer.disconnect();
  }, [Boolean(history)]);
  const points = history?.points ?? [], series = history ? selectionSeries(history, shares, name) : [];
  const maximum = shares ? 100 : Math.max(1, ...points.map(point => point.total ?? 0));
  const width = Math.max(760, viewportWidth), slot = (width - 24) / 8, x = (i: number) => 12 + slot * (i + .5);
  useLayoutEffect(() => { if (scroll.current) scroll.current.scrollLeft = scroll.current.scrollWidth - scroll.current.clientWidth; }, [width, history?.through_date]);
  const focusDay = (i: number) => { setActive(i); if (scroll.current) scroll.current.scrollLeft = Math.max(0, x(i) - scroll.current.clientWidth / 2); };
  return <section className="panel analytics-chart daily-selection-chart">
    <div className="section-title"><h2>{title}</h2><div className="device-chart-controls"><div className="chart-switch" role="group" aria-label={`${title}: результат подключения`}>{connectionOutcomes.map(value => <button key={value} aria-pressed={outcome === value} onClick={() => { setOutcome(value); setActive(null); }}>{outcomeLabels[value]}</button>)}</div><div className="chart-switch" role="group" aria-label={`${title}: единицы`}><button aria-pressed={!shares} onClick={() => setShares(false)}>Количество</button><button aria-pressed={shares} onClick={() => setShares(true)}>Доли, %</button></div></div></div>
    <CurrentDayNote date={source?.through_date} />
    {!history ? <p className="empty">{source ? "История для выбранного результата пока недоступна." : "Ежедневная история пока недоступна."}</p> : <>
      <div className="analytics-legend">{series.map(row => <span key={row.name}><svg width="12" height="12" aria-hidden="true"><rect width="12" height="12" rx="2" fill={row.color} /></svg>{row.name}</span>)}</div>
      <div className="analytics-plot" tabIndex={0} role="group" aria-label={`${title}. Стрелки влево и вправо — значения по дням.`}
        onFocus={() => focusDay(7)} onBlur={() => setActive(null)}
        onKeyDown={event => { if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); focusDay(Math.max(0, Math.min(7, (active ?? 7) + (event.key === "ArrowRight" ? 1 : -1)))); } }}>
        <div className="daily-device-plot"><svg className="device-chart-axis" width="44" height="256" aria-hidden="true">{[0, .5, 1].map(part => <text key={part} x="36" y={214 - 174 * part} textAnchor="end" className="chart-axis">{formatNumber(maximum * part)}{shares ? "%" : ""}</text>)}</svg>
          <div className="chart-scroll" ref={scroll}><svg className="chart-svg" viewBox={`0 0 ${width} 256`} style={{ width, minWidth: width }} role="img" aria-label={`${title}: распределение по дням`}
            onPointerLeave={() => setActive(null)} onPointerMove={event => { const rect = event.currentTarget.getBoundingClientRect(); setActive(Math.max(0, Math.min(7, Math.floor(((event.clientX - rect.left) * width / rect.width - 12) / slot)))); }}>
            {[0, .5, 1].map(part => <line key={part} x1="0" x2={width} y1={210 - 174 * part} y2={210 - 174 * part} className="chart-grid" />)}
            {points.map((point, i) => { let bottom = 210; return <g key={point.date} data-day={point.date} data-partial={point.partial || undefined} data-incomplete={!point.complete || undefined}>
              {point.partial && <rect x={x(i) - slot * .45} y="30" width={slot * .9} height="184" rx="3" fill="#f0e9fa" stroke="#5f22d9" strokeDasharray="3 3" />}
              {point.total === null && <line x1={x(i) - slot * .25} x2={x(i) + slot * .25} y1="210" y2="210" stroke="#9c9c9c" strokeWidth="3"><title>Нет данных</title></line>}
              {series.map(row => { const value = row.values[i]; if (value === null || value === 0) return null; const height = value / maximum * 174; bottom -= height; return <rect key={row.name} x={x(i) - slot * .36} y={bottom} width={slot * .72} height={height} fill={row.color}><title>{formatDay(point.date)} · {row.name}: {formatNumber(value)}{shares ? "%" : ""}</title></rect>; })}
              {!point.complete && point.total !== null && <rect x={x(i) - slot * .39} y={bottom - 2} width={slot * .78} height={Math.max(4, 212 - bottom)} fill="none" stroke="#9c9c9c" strokeDasharray="3 3"><title>Неполное покрытие истории</title></rect>}
              <text x={x(i)} y="236" textAnchor="middle" className="chart-axis">{formatDay(point.date)}</text>
              {point.partial && <text x={x(i)} y="252" textAnchor="middle" className="chart-axis">неполный день</text>}
            </g>; })}
            {active !== null && <line x1={x(active)} x2={x(active)} y1="30" y2="210" className="analytics-cursor" />}
          </svg></div>
        </div>
        {active !== null && points[active] && <div className="analytics-tooltip" role="tooltip"><strong>{formatDay(points[active].date)}{points[active].partial && " · неполный день"} · {outcomeLabels[outcome]}</strong>{points[active].total === null ? <div>Нет полной истории наблюдений</div> : <>{series.map(row => <div key={row.name}>{row.name}: <b>{formatNumber(row.values[active])}{shares && row.values[active] !== null ? "%" : ""}</b></div>)}{points[active].total === 0 && <div>Нет отметок в этот день</div>}</>}
          <div>Покрыто сессий: {points[active].observed_sessions} / {points[active].active_sessions}</div>
          {points[active].unknown_mode_sessions > 0 && <div>С неизвестным режимом: {points[active].unknown_mode_sessions}</div>}
          {points[active].uncertain_sessions > 0 && <div>Без времени завершения: {points[active].uncertain_sessions}</div>}
          {!points[active].complete && <div>Неполное покрытие истории</div>}
        </div>}
      </div>
      <p className="muted">Обновлено {date(history.generated_at)} GMT+3</p>
    </>}
    <p className="metric-definition">Каждый столбец — день, GMT+3. Успешная сессия учитывается один раз за каждый день, когда была подтверждена и открыта. Неуспешная — завершённая попытка без подтверждения подключения, включая отмену или истечение срока; учитывается один раз в день начала. «Все» объединяет эти группы; попытки без результата не включены. {explanation} Доли считаются внутри выбранной группы за день по известным отметкам. Пунктиром обозначено неполное покрытие; отсутствие истории не заменяется нулём. Тестовые аккаунты исключены.</p>
  </section>;
}
