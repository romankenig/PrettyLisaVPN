import { useState } from "react";
import { activeBars, aggregateSeries, chartSeries, type ChartMetric, type Point } from "./chart";
import type { FocusedHour, HistoryNode } from "./history";
import { date, TIME_ZONE_LABEL } from "./time";

const colors = ["#5f22d9", "#17655c", "#5b5b5b", "#2c016d", "#c82b28", "#d7ad0d"];
const number = (value: number) => new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 }).format(value);

export default function HistoryChart({ nodes, roster, end, onSelect, aggregate = false }: { nodes: HistoryNode[]; roster: HistoryNode[]; end: string | null; onSelect: (hour: FocusedHour) => void; aggregate?: boolean }) {
  const color = (id: string) => colors[Math.max(0, roster.findIndex(node => node.id === id)) % colors.length];
  const [metric, setMetric] = useState<ChartMetric>("speed");
  const series = aggregate ? aggregateSeries(nodes, metric) : chartSeries(nodes, metric);
  const points = series.flatMap(line => line.segments.flat());
  const start = Date.parse(nodes[0]?.history[0]?.at ?? "");
  const finish = end ? Date.parse(end) : NaN;
  const valid = points.length > 0 && Number.isFinite(start) && finish > start;
  const maximum = metric === "active" ? Math.max(4, Math.ceil(Math.max(0, ...points.map(point => point.value)) / 4) * 4) : metric === "rating" ? 100 : Math.max(1, Math.ceil(Math.max(0, ...points.map(point => point.value)) / 10) * 10);
  const x = (time: number) => 58 + 880 * (time - start) / (finish - start);
  const y = (value: number) => 238 - 210 * value / maximum;
  const bars = metric === "active" ? activeBars(series) : [];
  const hourWidth = 880 * 3600000 / (finish - start);
  const barWidth = hourWidth * 0.8 / (aggregate ? 1 : Math.max(1, nodes.length));
  const coverage = (point: Point) => aggregate ? ` · данные ${point.covered}/${point.total} серверов${point.covered !== point.total ? " (неполная выборка)" : ""}` : "";
  return <section className={`history-chart ${aggregate ? "panel" : "node-chart"}`} aria-label={aggregate ? "Общие показатели выбранных серверов" : `История сервера ${nodes[0]?.name ?? ""}`}>
    <div className="section-title"><div><h2>{aggregate ? metric === "active" ? "Активные устройства — сумма" : metric === "speed" ? "Средняя скорость" : "Медиана рейтинга" : metric === "active" ? "Активные устройства" : metric === "speed" ? "Скорость VPN" : "Рейтинг сервера"}</h2><p>За последние 7 дней · {TIME_ZONE_LABEL} · нажмите на {metric === "active" ? "столбик" : "точку"}, чтобы открыть проверку</p></div><div className="chart-switch" role="group" aria-label="Показатель графика"><button aria-pressed={metric === "speed"} onClick={() => setMetric("speed")}>Скорость</button><button aria-pressed={metric === "rating"} onClick={() => setMetric("rating")}>Рейтинг</button><button aria-pressed={metric === "active"} onClick={() => setMetric("active")}>Активные устройства</button></div></div>
    {valid ? <>
      <div className="chart-scroll"><svg className="chart-svg" viewBox="0 0 960 285" role="group" aria-label={metric === "active" ? "Количество активных VPN-подключений" : metric === "speed" ? "Скорость загрузки и отдачи, Мбит/с" : "Рейтинг от 0 до 100"}>
        <text x="58" y="14" className="chart-axis">{metric === "active" ? "устройства" : metric === "speed" ? "Мбит/с" : "баллы / 100"}</text>
        {[0, 1, 2, 3, 4].map(index => <g key={index}><line x1="58" x2="938" y1={y(maximum * index / 4)} y2={y(maximum * index / 4)} className="chart-grid" /><text x="48" y={y(maximum * index / 4) + 4} textAnchor="end" className="chart-axis">{number(maximum * index / 4)}</text></g>)}
        {[0, 1, 2, 3, 4, 5, 6].map(index => { const time = start + (finish - start) * index / 6; return <text key={index} x={x(time)} y="264" textAnchor={index === 0 ? "start" : index === 6 ? "end" : "middle"} className="chart-axis">{date(new Date(time).toISOString(), false)}</text>; })}
        {metric === "active" ? bars.map(point => {
          const label = `${point.nodeName}, ${date(new Date(point.time).toISOString())} ${TIME_ZONE_LABEL}: активные устройства ${number(point.value)}${coverage(point)}`;
          const select = () => onSelect({ at: new Date(point.hour).toISOString(), nodeId: aggregate ? undefined : point.nodeId });
          const offset = aggregate ? 0 : nodes.findIndex(node => node.id === point.nodeId);
          return <rect key={`${point.nodeId}-${point.hour}`} x={x(point.hour) + hourWidth * 0.1 + offset * barWidth} y={point.value === 0 ? y(0) - 1 : y(point.value)} width={barWidth * 0.9} height={Math.max(1, y(0) - y(point.value))} fill={color(point.nodeId)} role="button" tabIndex={0} aria-label={label} onClick={select} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); select(); } }}><title>{label}</title></rect>;
        }) : series.map(line => <g key={`${line.nodeId}-${line.direction}`} stroke={color(line.nodeId)}>{line.segments.map((segment, index) => <g key={index}><polyline fill="none" strokeWidth="2.2" strokeDasharray={line.direction === "upload" ? "6 4" : undefined} points={segment.map(point => `${x(point.time)},${y(point.value)}`).join(" ")} />{segment.map((point, item) => {
          const timestamp = new Date(point.time).toISOString();
          const label = `${line.nodeName}, ${date(timestamp)} ${TIME_ZONE_LABEL}: ${line.direction === "rating" ? "рейтинг" : line.direction === "download" ? "загрузка" : "отдача"} ${number(point.value)} ${metric === "speed" ? "Мбит/с" : "из 100"}${coverage(point)}`;
          const select = () => onSelect({ at: new Date(Math.floor(point.time / 3600000) * 3600000).toISOString(), nodeId: aggregate ? undefined : line.nodeId });
          return <circle key={item} cx={x(point.time)} cy={y(point.value)} r="3.5" fill="white" strokeWidth="2" role="button" tabIndex={0} aria-label={label} onClick={select} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); select(); } }}><title>{label}</title></circle>;
        })}</g>)}</g>)}
      </svg></div>
      <div className="chart-legend">{nodes.filter(node => series.some(line => line.nodeId === node.id && line.segments.length)).map(node => <span key={node.id}><svg width="10" height="10" aria-hidden="true"><circle cx="5" cy="5" r="4" fill={color(node.id)} /></svg>{node.name}</span>)}{metric === "speed" && <span className="chart-directions">Сплошная — загрузка ↓ · пунктир — отдача ↑</span>}</div>
      <p className="history-note">{aggregate ? "По последнему замеру каждого выбранного сервера за час: скорость — среднее, рейтинг — медиана, активные устройства — сумма. Пропуски не заменяются нулями; в подсказке указан охват. Неполная выборка не описывает всю группу. Подключение через посредника учитывается на обоих узлах." : metric === "active" ? "Каждый столбик — последнее измеренное число VPN-подключений на узле за час. Повторные проверки не суммируются, пропуски не заполняются." : "Каждая точка — сохранённый замер. Пропуски не заполняются; линия обрывается при отсутствии замера или перерыве более 75 минут."}</p>
    </> : <div className="empty"><h3>{metric === "active" ? "История активных устройств ещё не накоплена" : metric === "rating" ? "История рейтинга ещё не накоплена" : "Нет замеров скорости за выбранный период"}</h3><p>Данные появятся после проверки выбранных серверов. Неизвестные значения не заменяются нулями.</p></div>}
  </section>;
}
