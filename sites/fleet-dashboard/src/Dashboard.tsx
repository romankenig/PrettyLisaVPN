import { useCallback, useEffect, useState } from "react";
import { Check, ChevronDown, Clock3, LockKeyhole, RefreshCw, Server, ShieldCheck, X } from "lucide-react";
import { GROUPS, groupNames, groupSummaries, nodeGroup, type Group } from "./groups";
import HistoryChart from "./HistoryChart";
import HourDetails from "./HourDetails";
import type { Measurement, FocusedHour } from "./history";
import ClientDownloads from "./ClientDownloads";
import { readClients, type Clients } from "./downloads";
import { clock, date, TIME_ZONE_LABEL } from "./time";
import { selectionSummary } from "./summary";

type Status = "HEALTHY" | "DEGRADED" | "FAILED" | "UNKNOWN" | "PENDING" | "NOT_REGISTERED";
type Hour = { at: string; status: Status; modes: string[]; checks: number; measurements?: Measurement[] };
type Observation = { status: Status; mode: string; code: string; observed_at: string; active_connections: number; authorized_connections: number; handshake_ok: boolean | null; dns_ok: boolean | null; https_ok: boolean | null; egress_ok: boolean | null; connection_ms: number | null; download_mbps: number | null; upload_mbps: number | null; cleanup_confirmed: boolean };
type Node = { group?: Group; is_available_for_free?: boolean; id: string; name: string; country_code: string; configuration_state: string; quality: number; available: boolean; confidence: string; capacity: number; latest: Observation | null; latest_source_id: string | null; last_full_check_at: string | null; next_check_at: string | null; history: Hour[]; expected_hours: number; known_hours: number; successful_hours: number };
type Snapshot = { generated_at: string; nodes: Node[]; overall: object };
const names: Record<Status, string> = { HEALTHY: "Доступен", DEGRADED: "С ограничениями", FAILED: "Сбой", UNKNOWN: "Нет подтверждения", PENDING: "Ожидается проверка", NOT_REGISTERED: "Узел ещё не добавлен" };
const modes: Record<string, string> = { SYNTHETIC: "Межсерверная проверка", PASSIVE: "Действующие подключения", CONTROL: "Проверка управления" };
const number = (value: number | null | undefined, digits = 0) => value == null ? "—" : new Intl.NumberFormat("ru-RU", { maximumFractionDigits: digits }).format(value);
const percent = (part: number, total: number) => total ? `${number(100 * part / total, 1)}%` : "—";
function Timeline({ history, onSelect }: { history: Hour[]; onSelect: (hour: Hour) => void }) {
  return <div className="timeline" aria-label="Почасовая история за неделю">{history.map((hour) => <button key={hour.at} className={`hour ${hour.status}`} title={`${date(hour.at)} ${TIME_ZONE_LABEL} · ${names[hour.status]} · проверок: ${hour.checks}`} aria-label={`${date(hour.at)} ${TIME_ZONE_LABEL}: ${names[hour.status]}`} onClick={() => onSelect(hour)} />)}</div>;
}
function Proof({ label, value }: { label: string; value: boolean | null | undefined }) {
  return <span className={`proof ${value === true ? "yes" : value === false ? "no" : "unknown"}`}>{value === true ? <Check size={14} /> : value === false ? <X size={14} /> : <span>—</span>}{label}</span>;
}
export default function Dashboard() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [selected, setSelected] = useState("all");
  const [group, setGroup] = useState<Group | "all">("all");
  const [focused, setFocused] = useState<FocusedHour | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState(false);
  const [clients, setClients] = useState<Clients>({});
  const [downloadsUnavailable, setDownloadsUnavailable] = useState(false);
  const refreshClients = useCallback(async () => {
    try {
      const response = await fetch("/dashboard/downloads/index.json", { cache: "no-store" });
      if (!response.ok) throw new Error("unavailable");
      setClients(readClients(await response.json())); setDownloadsUnavailable(false);
    } catch { setDownloadsUnavailable(true); }
  }, []);
  const refresh = useCallback(async () => {
    void refreshClients();
    try {
      const response = await fetch("/dashboard/api/availability", { cache: "no-store" });
      if (!response.ok) throw new Error("unavailable");
      const data = await response.json() as Snapshot;
      if (!Array.isArray(data.nodes) || !data.overall) throw new Error("invalid");
      setSnapshot(data); setError(false);
    } catch { setError(true); } finally { setBusy(false); }
  }, [refreshClients]);
  useEffect(() => { const first = setTimeout(() => void refresh(), 0); const timer = setInterval(() => void refresh(), 60000); return () => { clearTimeout(first); clearInterval(timer); }; }, [refresh]);
  const groupNodes = snapshot?.nodes.filter(node => group === "all" || nodeGroup(node) === group) ?? [];
  const nodes = groupNodes.filter(node => selected === "all" || selected === node.id);
  const summary = selectionSummary(nodes);
  const known = nodes.reduce((sum, node) => sum + node.known_hours, 0), expected = nodes.reduce((sum, node) => sum + node.expected_hours, 0), successful = nodes.reduce((sum, node) => sum + node.successful_hours, 0);
  const combined = (nodes[0]?.history ?? []).map((hour, index) => {
    const values = nodes.map((node) => node.history[index]).filter((item) => item.status !== "NOT_REGISTERED");
    const status = (["FAILED", "DEGRADED", "UNKNOWN", "PENDING", "HEALTHY"] as Status[]).find((value) => values.some((item) => item.status === value)) ?? "NOT_REGISTERED";
    return { ...hour, status, checks: values.reduce((sum, value) => sum + value.checks, 0), modes: [...new Set(values.flatMap((value) => value.modes))] };
  });
  const newest = nodes.flatMap((node) => node.latest ? [node.latest] : []).sort((a, b) => b.observed_at.localeCompare(a.observed_at))[0];
  return <>
    <header className="topbar"><img src="/dashboard/logo.svg" alt="PrettyLisaVPN" width={236} height={54} /><div className="private"><LockKeyhole size={14} />Приватный мониторинг</div></header>
    <main className="workspace">
      <div className="heading"><div><div className="eyebrow">Инфраструктура / WireGuard</div><h1>Доступность VPN</h1><p>Последние 7 дней · почасовые проверки · время {TIME_ZONE_LABEL}</p></div><div className="controls"><label className="select"><select aria-label="Выбрать группу" value={group} onChange={event => { setGroup(event.target.value as Group | "all"); setSelected("all"); setFocused(null); }}><option value="all">Все группы</option>{GROUPS.map(value => <option key={value} value={value}>{groupNames[value]}</option>)}</select><ChevronDown size={15} /></label><label className="select"><Server size={17} /><select aria-label="Выбрать сервер" value={selected} onChange={(event) => { setSelected(event.target.value); setFocused(null); }}><option value="all">Все серверы</option>{groupNodes.map((node) => <option key={node.id} value={node.id}>{node.name} · {node.country_code}</option>)}</select><ChevronDown size={15} /></label><button className="refresh" onClick={() => { setBusy(true); void refresh(); }} disabled={busy} aria-label="Обновить"><RefreshCw size={18} className={busy ? "spin" : ""} /></button></div></div>
      {error && <div role="alert" className="notice">Не удалось получить свежие данные. {snapshot ? "Ниже показан последний полученный результат." : "Повторите обновление через минуту."}</div>}
      <section className="group-summaries" aria-label="Сводки по группам">{groupSummaries(snapshot?.nodes ?? []).map(summary => <button key={summary.group} className={`panel group-summary ${group === summary.group ? "selected" : ""}`} aria-pressed={group === summary.group} onClick={() => { setGroup(summary.group); setSelected("all"); setFocused(null); }}>
        <span>{groupNames[summary.group]}</span><strong>{summary.available} / {summary.servers} <small>доступно</small></strong><p>{summary.active != null && <>Активных: {summary.active} · </>}Успешность: {summary.availability == null ? "—" : number(summary.availability, 1) + "%"}</p>
        {summary.group === "INTERMEDIATE" && <p>Только транзит, без выбора в клиенте</p>}
      </button>)}</section>
      <section className="metrics" aria-label="Сводка доступности">
        <article className="metric featured"><span>Доступно сейчас</span><strong>{snapshot ? nodes.filter((node) => node.available).length : "—"}<small> / {snapshot ? nodes.length : "—"}</small></strong><p>Серверов с подтверждением</p><ShieldCheck className="metric-icon" size={57} strokeWidth={1} /></article>
        <article className="metric"><span>Успешность за неделю</span><strong>{snapshot ? percent(successful, known) : "—"}</strong><p>Среди часов с результатом</p></article>
        <article className="metric"><span>Покрытие наблюдениями</span><strong>{snapshot ? percent(known, expected) : "—"}</strong><p>{known} из {expected} завершённых часов</p></article>
        <article className="metric"><span>Последняя проверка</span><strong className="time">{newest ? clock(newest.observed_at) : "—"}</strong><p>{newest ? modes[newest.mode] : "Ожидаем первое наблюдение"}</p></article>
      </section>
      <section className="panel selection-summary" aria-label="Общие показатели выбранных серверов">
        <div><span>Средняя скорость ↓ / ↑</span><strong>{number(summary.download.value, 1)} / {number(summary.upload.value, 1)} <small>Мбит/с</small></strong><p>Данные: ↓ {summary.download.covered}/{nodes.length}, ↑ {summary.upload.covered}/{nodes.length} серверов</p></div>
        <div><span>Медиана рейтинга</span><strong>{number(summary.rating.value, 1)} <small>/ 100</small></strong><p>Данные: {summary.rating.covered}/{nodes.length} серверов</p></div>
        <div><span>Активные устройства — сумма</span><strong>{number(summary.active.value)}</strong><p>Данные: {summary.active.covered}/{summary.active.total} серверов FREE / PREMIUM{summary.active.covered < summary.active.total ? " · неполная выборка" : ""}</p></div>
      </section>
      <section className="panel history-panel"><div className="section-title"><div><h2>{selected !== "all" ? "История сервера" : group === "all" ? "Общая история" : `История группы ${groupNames[group]}`}</h2><p>Каждая отметка — час. Сбой любого выбранного узла виден в общей строке.</p></div><span className="period">7 дней</span></div>
        {combined.length ? <><div className="days">{combined.filter((_, i) => i % 24 === 0).map((hour) => <span key={hour.at}>{date(hour.at, false)}</span>)}</div><Timeline history={combined} onSelect={hour => setFocused({ at: hour.at })} /><div className="legend">{(["HEALTHY", "FAILED", "UNKNOWN", "NOT_REGISTERED"] as Status[]).map((status) => <span key={status}><i className={status} />{names[status]}</span>)}</div></> : <div className="empty"><Clock3 size={25} /><h3>{busy ? "Получаем историю…" : "История ещё не накоплена"}</h3><p>Новые серверы появятся после регистрации и настройки. Прошедшие часы не заполняются искусственно.</p></div>}
      </section>
      <HistoryChart aggregate nodes={nodes} roster={snapshot?.nodes ?? []} end={snapshot?.generated_at ?? null} onSelect={setFocused} />
      {focused && !focused.nodeId && <HourDetails focus={focused} nodes={nodes} />}
      <section className="nodes-section"><div className="section-title"><h2>Серверы <span className="count">{nodes.length}</span></h2><span className="muted">Автообновление каждую минуту</span></div>
        {nodes.map((node) => <article className="panel node" key={node.id}>
          <div className="node-heading"><div className="node-name"><span className="flag">{node.country_code === "DE" ? "🇩🇪" : node.country_code === "US" ? "🇺🇸" : node.country_code}</span><div><h3>{node.name}</h3><span>{groupNames[nodeGroup(node)]} · WireGuard · {node.country_code}</span></div></div><div className={`badge ${node.available ? "good" : "neutral"}`}>{node.available ? "Доступен" : node.confidence === "STALE" ? "Данные устарели" : node.latest?.status === "HEALTHY" ? "Недоступен для подключения" : node.latest ? names[node.latest.status] : "Ожидает проверки"}</div><div className="rating"><b>{node.quality}</b><span>рейтинг / 100</span></div></div>
          <div className="node-metrics"><div><span>Подключение</span><b>{number(node.latest?.connection_ms)} <small>мс</small></b></div><div><span>Скорость ↓ / ↑</span><b>{number(node.latest?.download_mbps, 1)} / {number(node.latest?.upload_mbps, 1)} <small>Мбит/с</small></b></div><div><span>Активные подключения</span><b>{number(node.latest?.active_connections)} <small>/ {node.capacity}</small></b></div><div><span>Следующая проверка</span><b className="date">{date(node.next_check_at)}</b></div></div>
          <div className="proofs"><span>{node.latest ? modes[node.latest.mode] : "Нет наблюдений"}</span><Proof label="Handshake" value={node.latest?.handshake_ok} /><Proof label="DNS" value={node.latest?.dns_ok} /><Proof label="HTTPS" value={node.latest?.https_ok} /><Proof label="Выходной IP" value={node.latest?.egress_ok} />{node.latest_source_id && <span>из {snapshot?.nodes.find((item) => item.id === node.latest_source_id)?.name ?? "другого узла"}</span>}</div>
          <Timeline history={node.history} onSelect={hour => setFocused({ at: hour.at, nodeId: node.id })} /><div className="node-footer"><span>Полная проверка: {date(node.last_full_check_at)} {TIME_ZONE_LABEL}</span><code>{node.latest?.code ?? node.configuration_state}</code></div>
          <HistoryChart nodes={[node]} roster={snapshot?.nodes ?? []} end={snapshot?.generated_at ?? null} onSelect={setFocused} />
          {focused?.nodeId === node.id && <HourDetails focus={focused} nodes={[node]} />}
        </article>)}
      </section>
      <ClientDownloads clients={clients} unavailable={downloadsUnavailable} />
      <footer><span><LockKeyhole size={13} />Только технические метрики. История посещений не собирается.</span><span>Данные: {date(snapshot?.generated_at ?? null)} {TIME_ZONE_LABEL}</span></footer>
    </main>
  </>;
}
