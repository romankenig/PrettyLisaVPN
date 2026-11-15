import { useState } from "react";
import { formatNumber } from "./analytics";
import CurrentDayNote from "./CurrentDayNote";

export default function BarDistribution({ title, items, explanation, partialDate }: { title: string; items: { name: string; count: number }[]; explanation: string; partialDate?: string }) {
  const [share, setShare] = useState(false);
  const total = items.reduce((sum, row) => sum + row.count, 0);
  const values = items.map(row => share ? (total ? row.count / total * 100 : 0) : row.count);
  const maximum = share ? 100 : Math.max(1, ...values);
  const width = Math.max(600, items.length * 90);
  return <section className="panel analytics-chart">
    <div className="section-title"><h2>{title}</h2><div className="chart-switch" aria-label={`${title}: единицы`} role="group"><button aria-pressed={!share} onClick={() => setShare(false)}>Количество</button><button aria-pressed={share} onClick={() => setShare(true)}>Доли, %</button></div></div>
    <CurrentDayNote date={partialDate} />
    {total ? <div className="chart-scroll"><svg viewBox={`0 0 ${width} 280`} style={{ minWidth: width }} role="group" aria-label={title}>
      {[0, .5, 1].map(part => <g key={part}><line x1="42" x2={width - 12} y1={210 - part * 170} y2={210 - part * 170} className="chart-grid"/><text x="36" y={214 - part * 170} textAnchor="end" className="chart-axis">{formatNumber(part * maximum)}</text></g>)}
      {items.map((row, i) => { const slot = (width - 60) / items.length, x = 48 + i * slot, height = values[i] / maximum * 170; return <g key={row.name} tabIndex={0} aria-label={`${row.name}: ${row.count}, ${formatNumber(100 * row.count / total)}%`}>
        <title>{row.name}: {row.count} · {formatNumber(100 * row.count / total)}%</title>
        <rect x={x + slot * .15} y={210 - height} width={slot * .7} height={height} rx="4" fill="#5f22d9"/>
        <text x={x + slot / 2} y={200 - height} textAnchor="middle" className="chart-axis">{formatNumber(values[i])}{share ? "%" : ""}</text>
        <text x={x + slot / 2} y="235" textAnchor="middle" className="chart-axis">{row.name.length > 14 ? row.name.slice(0, 13) + "…" : row.name}</text>
      </g>; })}
    </svg></div> : <p className="empty">Пока нет наблюдений для распределения.</p>}
    <p className="metric-definition">{explanation}</p>
  </section>;
}
