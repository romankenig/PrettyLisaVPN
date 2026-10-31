import { serviceColors, serviceIcons } from "./serviceIcons";
import { CurrentLocation } from "./CurrentLocation";
import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { t, useLanguage } from "../i18n";
import { useApplication } from "../state/application";
import {
  getDeviceTrafficSelection,
  normalizeMask,
  parseTrafficCatalog,
  refreshServices,
  routingPolicy,
  type TrafficSelection,
  type TrafficService,
  type TrafficMode as Mode,
} from "../vpn/traffic";
import { createHttpTransport } from "../native/http";

const labels: Record<Mode, string> = {
  all: "весь трафик",
  include: "только выбранные сайты",
  exclude: "кроме выбранных сайтов",
};
const details: Record<Mode, string> = {
  all: "все сайты и приложения через VPN",
  include: "остальной трафик — напрямую",
  exclude: "VPN для всего, кроме вашего списка",
};
export function TrafficRouting() {
  useLanguage();
  const { vpnConnection, session } = useApplication();
  const connection = useSyncExternalStore(
    vpnConnection.subscribe,
    vpnConnection.current,
    vpnConnection.current,
  );
  const store = getDeviceTrafficSelection();
  const selected = useSyncExternalStore(
    store.subscribe,
    store.current,
    store.current,
  );
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  async function save(next: TrafficSelection) {
    setBusy(true);
    setError(false);
    try {
      routingPolicy(next);
      routingPolicy({ ...next, mode: "include" });
      routingPolicy({ ...next, mode: "exclude" });
      const token = session.current()?.accessToken;
      if (!token) throw new Error("AUTH_REQUIRED");
      if (
        !["DISCONNECTED", "UNAVAILABLE"].includes(vpnConnection.current().phase)
      )
        await vpnConnection.disconnect(token);
      store.save(next);
      setOpen(false);
    } catch {
      setError(true);
      throw new Error("TRAFFIC_SAVE_FAILED");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="traffic-mode" aria-labelledby="traffic-mode-title">
      <div className="traffic-mode__heading">
        <h2 id="traffic-mode-title">{t("что защищаем")}</h2>
        <button
          type="button"
          className="traffic-edit"
          disabled={busy}
          onClick={() => setOpen(true)}
        >
          {t("Выбрать сервисы")} <span aria-hidden="true">›</span>
        </button>
      </div>
      <fieldset className="traffic-mode__options" disabled={busy}>
        <legend className="sr-only">{t("режим трафика")}</legend>
        {(["all", "include", "exclude"] as Mode[]).map((mode) => (
          <label
            key={mode}
            className={`traffic-choice ${mode === selected.mode ? "traffic-choice--active" : ""}`}
          >
            <input
              type="radio"
              aria-label={t(labels[mode])}
              name="traffic-mode"
              value={mode}
              checked={mode === selected.mode}
              onChange={() => {
                void save({ ...selected, mode }).catch(() => {});
              }}
            />
            <span>
              {t(
                mode === "all"
                  ? "Всё"
                  : mode === "include"
                    ? "Выбранное"
                    : "Кроме выбранного",
              )}
            </span>
          </label>
        ))}
      </fieldset>
      <p className="traffic-mode__hint">{t(details[selected.mode])}</p>
      {selected.mode !== "all" && (
        <SelectedServiceIcons
          items={[
            ...selected[selected.mode].services.map((service) => ({
              id: service.id,
              name: service.name,
              icon: service.icon,
            })),
            ...selected[selected.mode].masks.map((mask) => ({
              id: mask,
              name: mask,
              icon: "website",
            })),
          ]}
        />
      )}
      {error && (
        <p role="alert">
          {t("Не удалось сохранить правила. Повторите попытку.")}
        </p>
      )}
      {selected.mode !== "all" && (
        <CurrentLocation connection={connection} vpn />
      )}
      {open && (
        <TrafficDialog
          initial={selected}
          busy={busy}
          error={error}
          onClose={() => setOpen(false)}
          onSave={save}
        />
      )}
    </section>
  );
}
function SelectedServiceIcons({
  items,
}: {
  items: { id: string; name: string; icon: string }[];
}) {
  const container = useRef<HTMLDivElement>(null);
  const [slots, setSlots] = useState<number | null>(null);
  useLayoutEffect(() => {
    const node = container.current;
    if (!node) return;
    const measure = () => {
      const width = node.getBoundingClientRect().width;
      if (width > 0) setSlots(Math.max(1, Math.floor((width + 4) / 24)));
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  const logos = items.filter((item) => serviceIcons[item.icon]);
  const needsMore =
    logos.length < items.length || (slots !== null && logos.length > slots);
  const visible = logos.slice(
    0,
    slots === null ? logos.length : Math.max(0, slots - (needsMore ? 1 : 0)),
  );
  const hidden = items
    .filter((item) => !visible.includes(item))
    .map((item) => item.name)
    .join(", ");
  return (
    <div
      ref={container}
      className="traffic-selected"
      aria-label={t("Выбранные сервисы")}
    >
      {visible.map((item) => (
        <span
          key={item.id}
          className="traffic-selected__icon"
          style={{ color: serviceColors[item.icon] ?? serviceColors.website }}
          role="img"
          aria-label={item.name}
          title={item.name}
        >
          <ServiceIcon name={item.icon} />
        </span>
      ))}
      {hidden && (
        <span
          className="traffic-selected__more"
          role="img"
          aria-label={hidden}
          title={hidden}
        >
          …
        </span>
      )}
    </div>
  );
}
function ServiceIcon({ name }: { name: string }) {
  if (serviceIcons[name])
    return (
      <svg
        aria-hidden="true"
        width="26"
        height="26"
        viewBox="0 0 24 24"
        fill="currentColor"
      >
        <path d={serviceIcons[name]} />
      </svg>
    );
  const badge: Record<string, string> = {
    linkedin: "in",
    max: "M",
    yandex: "Я",
    ozon: "O",
    wildberries: "WB",
    gosuslugi: "ГУ",
    rutube: "R",
    dzen: "Д",
  };
  if (badge[name])
    return (
      <svg aria-hidden="true" width="26" height="26" viewBox="0 0 24 24">
        <rect width="24" height="24" rx="6" fill="currentColor" />
        <text
          x="12"
          y="16"
          textAnchor="middle"
          fill="white"
          fontSize="11"
          fontWeight="600"
        >
          {badge[name]}
        </text>
      </svg>
    );
  return (
    <svg
      aria-hidden="true"
      width="28"
      height="28"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
    >
      <circle cx="12" cy="12" r="9" />
      <ellipse cx="12" cy="12" rx="4" ry="9" />
      <path d="M3 12h18" />
    </svg>
  );
}
function TrafficDialog({
  initial,
  busy,
  error,
  onClose,
  onSave,
}: {
  initial: TrafficSelection;
  busy: boolean;
  error: boolean;
  onClose: () => void;
  onSave: (v: TrafficSelection) => Promise<void>;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const app = useApplication();
  const [draft, setDraft] = useState(() => structuredClone(initial));
  const [tab, setTab] = useState<"include" | "exclude">(
    initial.mode === "exclude" ? "exclude" : "include",
  );
  const [catalog, setCatalog] = useState<TrafficService[]>([]);
  const [loading, setLoading] = useState(true);
  const [unavailable, setUnavailable] = useState(false);
  const [query, setQuery] = useState("");
  const [input, setInput] = useState("");
  const [invalid, setInvalid] = useState(false);
  useEffect(() => {
    const old = document.activeElement as HTMLElement | null;
    dialog.current?.showModal();
    return () => old?.focus();
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const token = await app.session.bearer(app.api);
        const response = await createHttpTransport()(
          new URL("/vpn/traffic/services", app.config.backendBaseUrl),
          {
            headers: { Authorization: `Bearer ${token}` },
            signal: AbortSignal.any([
              controller.signal,
              AbortSignal.timeout(15000),
            ]),
            cache: "no-store",
          },
        );
        if (!response.ok) throw new Error("CATALOG_UNAVAILABLE");
        const data = parseTrafficCatalog(await response.json());
        if (!controller.signal.aborted) setCatalog(data);
      } catch {
        if (!controller.signal.aborted) setUnavailable(true);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();
    return () => controller.abort();
  }, [app]);
  const list = draft[tab];
  const services = [
    ...catalog,
    ...list.services.filter((s) => !catalog.some((c) => c.id === s.id)),
  ];
  return (
    <dialog
      ref={dialog}
      className="traffic-dialog"
      aria-labelledby="traffic-dialog-title"
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) onClose();
      }}
    >
      <h2 id="traffic-dialog-title">{t("Выбрать сервисы")}</h2>
      <p>
        {t(
          "При сохранении VPN отключится. Новые правила — со следующего подключения.",
        )}
      </p>
      <div
        className="traffic-tabs"
        role="group"
        aria-label={t("режим трафика")}
      >
        {(["include", "exclude"] as const).map((mode) => (
          <button
            key={mode}
            type="button"
            aria-pressed={tab === mode}
            disabled={busy}
            onClick={() => {
              setTab(mode);
              setInput("");
              setInvalid(false);
            }}
          >
            {t(labels[mode])}
          </button>
        ))}
      </div>
      <div className="traffic-dialog__body">
        {loading && <p role="status">{t("Загрузка сервисов…")}</p>}
        {unavailable && (
          <p role="status">
            {t(
              "Каталог недоступен. Сохранённые сервисы и ваши маски доступны.",
            )}
          </p>
        )}
        <input
          className="traffic-search"
          type="search"
          aria-label={t("Найти сервис")}
          placeholder={t("Найти сервис")}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        {(["popular", "whitelist"] as const).map((category) => (
          <section key={category} className="traffic-category">
            <h3>
              {t(
                category === "popular" ? "Популярные сервисы" : "Белый список",
              )}
            </h3>
            <div className="traffic-services">
              {services
                .filter(
                  (service) =>
                    (service.category ?? "popular") === category &&
                    service.name
                      .toLocaleLowerCase()
                      .includes(query.trim().toLocaleLowerCase()),
                )
                .map((service) => (
                  <label key={service.id}>
                    <input
                      type="checkbox"
                      role="switch"
                      className="service-switch"
                      aria-label={service.name}
                      checked={list.services.some((s) => s.id === service.id)}
                      disabled={busy}
                      onChange={() =>
                        setDraft({
                          ...draft,
                          [tab]: {
                            ...list,
                            services: list.services.some(
                              (s) => s.id === service.id,
                            )
                              ? list.services.filter((s) => s.id !== service.id)
                              : [...list.services, service],
                          },
                        })
                      }
                    />
                    <ServiceIcon name={service.icon} />
                    <span>{service.name}</span>
                  </label>
                ))}
            </div>
          </section>
        ))}
        <label htmlFor="traffic-mask">{t("Маска сервиса")}</label>
        <div className="traffic-mask-entry">
          <input
            id="traffic-mask"
            value={input}
            disabled={busy}
            placeholder="youtube.com, *.youtube.com"
            onChange={(e) => setInput(e.target.value)}
          />
          <button
            type="button"
            disabled={busy || !input.trim()}
            onClick={() => {
              try {
                const masks = input.split(/[,\n]+/).map(normalizeMask);
                if (list.masks.length + masks.length > 256) throw new Error();
                setDraft({
                  ...draft,
                  [tab]: {
                    ...list,
                    masks: [...new Set([...list.masks, ...masks])],
                  },
                });
                setInput("");
                setInvalid(false);
              } catch {
                setInvalid(true);
              }
            }}
          >
            {t("Добавить")}
          </button>
        </div>
        {invalid && (
          <p role="alert">
            {t(
              "Укажите домен или *.домен, без адреса страницы. Максимум 256 масок.",
            )}
          </p>
        )}
        <ul className="traffic-masks">
          {list.masks.map((mask) => (
            <li key={mask}>
              <span>{mask}</span>
              <button
                type="button"
                disabled={busy}
                aria-label={`${t("Удалить")} ${mask}`}
                onClick={() =>
                  setDraft({
                    ...draft,
                    [tab]: {
                      ...list,
                      masks: list.masks.filter((m) => m !== mask),
                    },
                  })
                }
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      </div>
      {error && (
        <p role="alert">
          {t("Не удалось сохранить правила. Повторите попытку.")}
        </p>
      )}
      <div className="traffic-dialog__actions">
        <button type="button" disabled={busy} onClick={onClose}>
          {t("Отмена")}
        </button>
        <button
          type="button"
          disabled={busy || !!input.trim()}
          onClick={() => {
            void onSave(refreshServices(draft, catalog)).catch(() => {});
          }}
        >
          {t("Сохранить")}
        </button>
      </div>
    </dialog>
  );
}
