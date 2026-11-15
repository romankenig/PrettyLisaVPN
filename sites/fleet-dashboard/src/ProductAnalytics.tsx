import { useEffect, useState } from "react";
import { ArrowLeft, Clock3, LockKeyhole, RefreshCw } from "lucide-react";
import AnalyticsChart from "./AnalyticsChart";
import BarDistribution from "./BarDistribution";
import DailyDeviceDistribution from "./DailyDeviceDistribution";
import { formatDay, formatNumber, plans, planShare, readAnalytics, type ActiveMetric, type Analytics } from "./analytics";
import { date } from "./time";

const planNames = { DEMO: "DEMO", FREE: "Free", PREMIUM: "Premium", PLATINUM: "Platinum", UNKNOWN: "Тариф неизвестен" };
const planColors = { DEMO: "#d3618e", FREE: "#17655c", PREMIUM: "#5f22d9", PLATINUM: "#b28a09", UNKNOWN: "#9c9c9c" };
const durationLabels = ["≤10 с", "10–60 с", "1–3 мин", "3–5 мин", "5–15 мин", ">15 мин"];
const colors = { mau: "#5f22d9", wau: "#17655c", dau: "#d7ad0d" };
const widths = { dau: 1, wau: 7, mau: 30 };
const definition = (metric: ActiveMetric) => `${metric.toUpperCase()} — уникальные аккаунты с успешным авторизованным обращением за ${widths[metric]} ${metric === "dau" ? "день" : "дней"}, включая дату точки. Обновление токена и VPN heartbeat также считаются активностью. Несколько устройств одного аккаунта считаются один раз.`;

export default function ProductAnalytics() {
  useEffect(() => { document.title = "PrettyLisaVPN — Продуктовая аналитика"; }, []);
  const [data, setData] = useState<Analytics | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  const [planShares, setPlanShares] = useState(true);
  useEffect(() => {
    const controller = new AbortController(); let timer: ReturnType<typeof setTimeout> | undefined;
    void (async () => {
      try {
        const response = await fetch("/dashboard/api/product-analytics", { cache: "no-store", signal: controller.signal });
        if (!response.ok) throw new Error("Unavailable");
        const value = readAnalytics(await response.json());
        if (controller.signal.aborted) return;
        setData(value); setError(false);
        // Data is computed once per day on the main server, not in this page.
        timer = setTimeout(() => setRetry(v => v + 1), Math.max(300_000, Date.parse(value.next_update_at) + 90_000 - Date.now()));
      } catch { if (!controller.signal.aborted) setError(true); }
      finally { if (!controller.signal.aborted) setLoading(false); }
    })();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [retry]);
  const points = data?.points ?? [], last = points.at(-1), dates = points.map(point => point.date);
  const stale = data && Date.now() > Date.parse(data.next_update_at) + 15 * 60_000;
  return <>
    <header className="topbar"><a href="/dashboard/"><img src="/dashboard/logo.svg" alt="PrettyLisaVPN" width={236} height={54} /></a><div className="private"><LockKeyhole size={14} />Приватная аналитика</div></header>
    <main className="workspace product-analytics">
      <a className="analytics-back" href="/dashboard/"><ArrowLeft size={16} />Доступность серверов</a>
      <div className="heading"><div><div className="eyebrow">Продукт / Аудитория</div><h1>Как используют PrettyLisaVPN</h1><p>Два месяца · по дням · время GMT+3{data && <> · по {formatDay(data.through_date)} включительно</>}</p></div><button className="refresh" disabled={loading} aria-label="Получить сохранённые данные" onClick={() => { setLoading(true); setRetry(v => v + 1); }}><RefreshCw size={18} className={loading ? "spin" : ""} /></button></div>
      <div className="analytics-updated"><Clock3 size={15} />{data ? <>Обновлено {date(data.generated_at)} GMT+3 · следующее обновление {date(data.next_update_at)} GMT+3</> : "Ожидаем первый ежедневный расчёт"}</div>
      {error && <div role="alert" className="notice">Не удалось получить сохранённые метрики. {data ? "Показан предыдущий результат." : "Повторите загрузку позже."}</div>}
      {stale && <div role="status" className="notice">Ежедневное обновление задерживается. Последняя рассчитанная дата: {formatDay(data.through_date)}.</div>}
      {data?.history_partial && <div className="analytics-coverage">Исторические данные неполные: раньше сохранялись только входы, обновления токенов и отдельные события VPN. Полный сбор авторизованной активности — с {formatDay(data.full_collection_from)}. Неизвестные тарифы показаны отдельно; разрывы на графике означают отсутствие истории, а не ноль.</div>}
      <section className="metrics analytics-cards" aria-label="Последний завершённый день">
        {(["mau", "wau", "dau"] as ActiveMetric[]).map(metric => <article className={`metric ${metric === "mau" ? "featured" : ""}`} key={metric}><span>{metric.toUpperCase()}{last && ` · ${formatDay(last.date)}`}</span><strong>{formatNumber(last?.[metric].total)}</strong><p>{definition(metric)}</p></article>)}
        <article className="metric"><span>Новые аккаунты{last && ` · ${formatDay(last.date)}`}</span><strong>{formatNumber(last?.new_accounts)}</strong><p>Аккаунты, созданные в этот календарный день. Тестовые адреса исключены.</p></article>
      </section>
      {data && <>
        <AnalyticsChart title="Динамика активной аудитории" dates={dates} series={(["mau", "wau", "dau"] as ActiveMetric[]).map(metric => ({ name: metric.toUpperCase(), color: colors[metric], values: points.map(p => p[metric].total) }))} explanation="Каждая точка — завершённый день. DAU: 1 день, WAU: 7 дней, MAU: 30 дней до точки включительно. Это уникальные аккаунты, не сумма устройств и не сумма ежедневных значений." />
        <div className="chart-switch" role="group" aria-label="Распределение тарифов"><button aria-pressed={planShares} onClick={() => setPlanShares(true)}>Доли тарифов, %</button><button aria-pressed={!planShares} onClick={() => setPlanShares(false)}>Количество</button></div>
        <div className="analytics-cohorts">{(["mau", "wau", "dau"] as ActiveMetric[]).map(metric => <AnalyticsChart key={metric} title={`${metric.toUpperCase()} по тарифам`} dates={dates} unit={planShares ? "%" : ""} series={plans.map(plan => ({ name: planNames[plan], color: planColors[plan], values: points.map(p => planShares ? planShare(p[metric], plan) : p[metric].plans[plan]), dashed: plan === "UNKNOWN" }))} explanation={`${definition(metric)} DEMO — гостевые аккаунты. Доля — категория / вся активная аудитория окна × 100%. Тариф берётся на момент последней активности; неизвестные исторические тарифы не заменяются текущими.`} />)}</div>
        <DailyDeviceDistribution points={points} />
        <AnalyticsChart title="Средняя длительность подключения" dates={dates} unit=" с" series={[{ name: "От подключения до отключения", color: "#5f22d9", values: points.map(point => point.mean_session_seconds ?? null) }]} explanation={`Среднее по завершённым сессиям, по дате отключения. Начало — подтверждение VPN; конец — запрос отключения или прекращение доступа сервером. Открытые сессии и старая история без времени отключения исключены. Среднее по сессиям, начавшимся за период: ${formatNumber(data.mean_session_seconds)} с.`} />
        <div className="analytics-extras">
          <BarDistribution title="Длительность подключения" items={(data.session_duration?.counts ?? []).map((count, i) => ({ name: durationLabels[i], count }))} explanation={`От подключения до отключения для сессий, начавшихся за период. Верхняя граница интервала включена. Без конечного наблюдения: ${formatNumber(data.duration_unobserved_sessions)}.`} />
          <BarDistribution title="Время до первой тишины" items={(data.time_to_silence?.counts ?? []).map((count, i) => ({ name: durationLabels[i], count }))} explanation={`От подключения до начала первых 10 секунд без изменения счётчиков байтов. Измерения примерно каждые 5 секунд; пропуски не считаются тишиной. Без подтверждённого первого периода тишины: ${formatNumber(data.silence_unobserved_sessions)}.`} />
        </div>
        <div className="analytics-extras">
          <AnalyticsChart title="Новые аккаунты" dates={dates} series={[{ name: "Регистрации", color: "#5f22d9", values: points.map(p => p.new_accounts) }]} explanation="Число аккаунтов по дате создания (GMT+3), без зарезервированных тестовых доменов. Повторный вход не является новой регистрацией." />
          <AnalyticsChart title="Подтверждённые подключения VPN" dates={dates} series={[{ name: "Подключения", color: "#17655c", values: points.map(p => p.verified_sessions) }]} explanation="Количество клиентских VPN-сессий по дате подтверждения доступа в Интернет. Установка peer и старый статус ACTIVE не считаются подтверждением. Автоматические проверки серверов исключены." />
          <AnalyticsChart title="Успешность подключения" dates={dates} unit="%" series={[{ name: "Успешность", color: "#5f22d9", values: points.map(p => p.connection_success_percent) }]} explanation="Подтверждённые / завершённые попытки × 100%, сгруппированные по дате начала. Каждый кандидат автоматического перебора — отдельная попытка. Незавершённые попытки исключены; при отсутствии попыток — нет значения." />
          <AnalyticsChart title="Регулярность использования · DAU/MAU" dates={dates} unit="%" series={[{ name: "DAU/MAU", color: "#17655c", values: points.map(p => p.engagement_percent) }]} explanation="Доля месячной активной аудитории, активная в день точки: DAU / MAU × 100%. Это показатель регулярности использования, а не удержания когорты. При MAU = 0 значения нет." />
        </div>
        <p className="analytics-footnote">Все показатели исключают тестовые аккаунты. История посещений, адреса сайтов, DNS-запросы и содержимое трафика не собираются. Расчёт выполняется ежедневно на основном сервере; текущий незавершённый день не отображается.</p>
      </>}
    </main>
  </>;
}
