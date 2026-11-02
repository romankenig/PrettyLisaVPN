import { useLayoutEffect, useRef, useState } from "react";
import { formatDay, formatNumber, segments, type Series } from "./analytics";

export default function AnalyticsChart({ title, dates, series, explanation, unit = "" }: { title: string; dates: string[]; series: Series[]; explanation: string; unit?: string }) {
  const plot = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(760);
  useLayoutEffect(() => {
    const node = plot.current;
    if (!node) return;
    const measure = () => setWidth(Math.max(240, node.getBoundingClientRect().width));
    measure(); const observer = new ResizeObserver(measure); observer.observe(node);
    return () => observer.disconnect();
  }, []);
  const [active, setActive] = useState<number | null>(null);
  const maximum = Math.max(1, ...series.flatMap(line => line.values.filter((value): value is number => value !== null)));
  const x = (index: number) => 44 + (width - 68) * index / Math.max(1, dates.length - 1);
  const y = (value: number) => 208 - 174 * value / maximum;
  const index = active === null ? null : Math.min(dates.length - 1, active);
  return <section className="panel analytics-chart">
    <h2>{title}</h2>
    <div className="analytics-legend">{series.map(line => <span key={line.name}><svg width="18" height="8" aria-hidden="true"><path d="M0 4H18" stroke={line.color} strokeWidth="3" strokeDasharray={line.dashed ? "3 2" : undefined} /></svg>{line.name}</span>)}</div>
    <div ref={plot} className="analytics-plot" tabIndex={0} role="group" aria-label={`${title}. Стрелки влево и вправо — значения по дням.`}
      onFocus={() => setActive(dates.length - 1)} onBlur={() => setActive(null)}
      onKeyDown={event => { if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); setActive(Math.max(0, Math.min(dates.length - 1, (index ?? dates.length - 1) + (event.key === "ArrowRight" ? 1 : -1)))); } }}>
      <svg viewBox={`0 0 ${width} 244`} role="img" aria-label={title} onPointerLeave={() => setActive(null)} onPointerMove={event => {
        const rect = event.currentTarget.getBoundingClientRect();
        setActive(Math.max(0, Math.min(dates.length - 1, Math.round(((event.clientX - rect.left) * width / rect.width - 44) / (width - 68) * (dates.length - 1)))));
      }}>
        {[0, 0.5, 1].map(fraction => <g key={fraction}><path d={`M44 ${y(maximum * fraction)}H${width - 24}`} className="analytics-grid" /><text x="36" y={y(maximum * fraction) + 4} textAnchor="end" className="analytics-axis">{formatNumber(maximum * fraction)}</text></g>)}
        {[0, Math.floor((dates.length - 1) / 2), dates.length - 1].map(i => <text key={i} x={x(i)} y="234" textAnchor={i === 0 ? "start" : i === dates.length - 1 ? "end" : "middle"} className="analytics-axis">{formatDay(dates[i])}</text>)}
        {series.map(line => <g key={line.name}>{segments(line.values).map((segment, i) => <g key={i}>
          <path d={segment.map((p, n) => `${n ? "L" : "M"}${x(p.index)},${y(p.value)}`).join(" ")} fill="none" stroke={line.color} strokeWidth="2.4" strokeDasharray={line.dashed ? "5 4" : undefined} />
          {segment.map(p => <circle key={p.index} cx={x(p.index)} cy={y(p.value)} r={index === p.index ? 4.5 : 2} fill={line.color} />)}
        </g>)}</g>)}
        {index !== null && <path d={`M${x(index)} 28V208`} className="analytics-cursor" />}
      </svg>
      {index !== null && <div className="analytics-tooltip" role="tooltip"><strong>{formatDay(dates[index])} {dates[index].slice(0, 4)}</strong>{series.map(line => <div key={line.name}>{line.name}: <b>{formatNumber(line.values[index])}{line.values[index] !== null ? unit : ""}</b></div>)}</div>}
    </div>
    <p className="metric-definition">{explanation}</p>
  </section>;
}
