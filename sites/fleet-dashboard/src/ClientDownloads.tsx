import { Download, Globe, Monitor, Smartphone } from "lucide-react";
import { downloadUrls, sourceUrls, simulatorUrl, platformNames, packageLabels, installNotes, PLATFORMS, type Clients } from "./downloads";
import { date, TIME_ZONE_LABEL } from "./time";

export default function Downloads({ clients, unavailable }: { clients: Clients; unavailable: boolean }) {
  return <section className="panel downloads" aria-label="Скачать клиенты">
    <div className="section-title"><div><h2>Скачать PrettyLisaVPN</h2><p>Последние проверенные версии для тестирования. Ссылки обновляются автоматически.</p></div></div>
    {unavailable && <p role="status" className="muted">Список версий временно недоступен. Повторите обновление.</p>}
    <div className="download-list">{PLATFORMS.map(platform => {
      const client = clients[platform];
      return <article className="download-client" key={platform}>
        {platform === "chrome" ? <Globe size={23} /> : platform === "android" || platform === "ios" ? <Smartphone size={23} /> : <Monitor size={23} />}
        <div><h3>{platformNames[platform]}{client?.abi && " · ARM64"}{client && <span>{client.version}</span>}</h3><p>{client ? `${new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 }).format(client.bytes / 1048576)} МБ · ${date(client.published_at)} ${TIME_ZONE_LABEL}` : "Сборка пока недоступна"}</p><p>{installNotes[platform]}</p></div>
        {client && <div className="download-actions">
          {platform === "ios" && client.has_simulator && <a href={simulatorUrl} download aria-label="Скачать iOS Simulator ZIP"><Download size={16} />Симулятор</a>}
          <a href={downloadUrls[platform]} download aria-label={`Скачать ${platformNames[platform]} ${platform === "ios" ? "для iPhone ZIP" : packageLabels[platform]}`}><Download size={16} />{platform === "ios" ? "iPhone" : packageLabels[platform]}</a>
        </div>}
      </article>;
    })}</div>
    {PLATFORMS.some(platform => clients[platform]?.has_sources) && <p className="download-help">Исходники и лицензии: {PLATFORMS.filter(platform => clients[platform]?.has_sources).map((platform, index) => <span key={platform}>{index > 0 && " · "}<a href={sourceUrls[platform]} download>{platformNames[platform]}</a></span>)}</p>}
  </section>;
}
