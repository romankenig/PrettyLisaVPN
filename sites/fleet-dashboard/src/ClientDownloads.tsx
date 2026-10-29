import { Download, Monitor, Smartphone } from "lucide-react";
import { downloadUrls, sourceUrls, PLATFORMS, type Clients } from "./downloads";
import { date, TIME_ZONE_LABEL } from "./time";

export default function Downloads({ clients, unavailable }: { clients: Clients; unavailable: boolean }) {
  return <section className="panel downloads" aria-label="Скачать клиенты">
    <div className="section-title"><div><h2>Скачать PrettyLisaVPN</h2><p>Последние проверенные версии для тестирования. Ссылки обновляются автоматически.</p></div></div>
    {unavailable && <p role="status" className="muted">Список версий временно недоступен. Повторите обновление.</p>}
    <div className="download-list">{PLATFORMS.map(platform => {
      const client = clients[platform];
      return <article className="download-client" key={platform}>
        {platform === "android" ? <Smartphone size={23} /> : <Monitor size={23} />}
        <div><h3>{platform === "android" ? "Android" : "Windows"}{client && <span>{client.version}</span>}</h3><p>{client ? `${new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 }).format(client.bytes / 1048576)} МБ · ${date(client.published_at)} ${TIME_ZONE_LABEL}` : "Сборка пока недоступна"}</p></div>
        {client && <a href={downloadUrls[platform]} download aria-label={`Скачать ${platform === "android" ? "Android APK" : "Windows EXE"}`}><Download size={16} />{platform === "android" ? "APK" : "EXE"}</a>}
      </article>;
    })}</div>
    <p className="download-help">Android: установите APK поверх приложения. Windows: сохраните и запустите EXE.</p>
    {PLATFORMS.some(platform => clients[platform]?.has_sources) && <p className="download-help">Исходники и лицензии: {PLATFORMS.filter(platform => clients[platform]?.has_sources).map((platform, index) => <span key={platform}>{index > 0 && " · "}<a href={sourceUrls[platform]} download>{platform === "android" ? "Android" : "Windows"}</a></span>)}</p>}
  </section>;
}
