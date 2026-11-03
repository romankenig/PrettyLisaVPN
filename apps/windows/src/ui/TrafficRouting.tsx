import { serviceColors, serviceIcons } from "./serviceIcons";
import { CurrentLocation } from "./CurrentLocation";
import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { t, useLanguage, getLanguage } from "../i18n";
import { serviceGroups } from "../vpn/serviceGroups";
import { useApplication } from "../state/application";
import {
  getDeviceTrafficSelection,
  normalizeMask,
  parseTrafficCatalog,
  refreshServices,
  seedTrafficDefaults,
  routingPolicy,
  type TrafficSelection,
  type TrafficService,
  type TrafficMode as Mode,
} from "../vpn/traffic";
import { createHttpTransport } from "../native/http";

const shortLabels: Record<Mode, string> = {
  all: "Всё",
  include: "Выбранное",
  exclude: "Кроме выбранного",
};
export function TrafficRouting({
  refreshKey = 0,
}: {
  readonly refreshKey?: number;
}) {
  useLanguage();
  const { vpnConnection, session, api, config } = useApplication();
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
  useEffect(() => {
    if (
      !selected.preset_defaults ||
      (selected.mode !== "all" &&
        !["DISCONNECTED", "UNAVAILABLE"].includes(connection.phase))
    )
      return;
    const controller = new AbortController();
    void (async () => {
      try {
        const appToken = await session.bearer(api);
        const response = await createHttpTransport()(
          new URL("/vpn/traffic/services", config.backendBaseUrl),
          {
            headers: { Authorization: `Bearer ${appToken}` },
            signal: AbortSignal.any([
              controller.signal,
              AbortSignal.timeout(15000),
            ]),
            cache: "no-store",
          },
        );
        if (!response.ok || controller.signal.aborted) return;
        const next = seedTrafficDefaults(
          store.current(),
          parseTrafficCatalog(await response.json()),
        );
        if (!controller.signal.aborted && next !== store.current())
          store.save(next);
      } catch {
        /* Retry when Home is refreshed; a failed fetch never marks defaults saved. */
      }
    })();
    return () => controller.abort();
  }, [
    selected.preset_defaults,
    selected.mode,
    connection.phase,
    refreshKey,
    session,
    store,
    config.backendBaseUrl,
    api,
  ]);
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
        <select
          className="traffic-mode__select"
          aria-label={t("режим трафика")}
          aria-describedby={
            selected.mode === "all" ? "traffic-mode-description" : undefined
          }
          value={selected.mode}
          disabled={busy}
          onChange={(event) => {
            void save({ ...selected, mode: event.target.value as Mode }).catch(
              () => {},
            );
          }}
        >
          {(["all", "include", "exclude"] as Mode[]).map((mode) => (
            <option key={mode} value={mode}>
              {t(shortLabels[mode])}
            </option>
          ))}
        </select>
      </div>
      {selected.mode === "all" && (
        <p id="traffic-mode-description" className="traffic-mode__hint">
          {t("все сайты и приложения через VPN")}
        </p>
      )}
      {selected.mode !== "all" && (
        <>
          <button
            type="button"
            className="traffic-edit"
            disabled={busy}
            onClick={() => setOpen(true)}
          >
            {t("Выбрать сервисы")}
          </button>
          <p className="traffic-selected-label">{t("Выбранные сервисы:")}</p>
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
        </>
      )}
      {error && (
        <p role="alert">
          {t("Не удалось сохранить правила. Повторите попытку.")}
        </p>
      )}
      {selected.mode !== "all" && (
        <CurrentLocation
          connection={connection}
          vpn
          direct={selected.mode === "exclude"}
          refreshKey={refreshKey}
        />
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
        style={{ color: serviceColors[name] ?? serviceColors.website }}
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
      <svg
        aria-hidden="true"
        width="26"
        height="26"
        viewBox="0 0 24 24"
        style={{ color: serviceColors[name] ?? serviceColors.website }}
      >
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
  const [tab] = useState<"include" | "exclude">(
    initial.mode === "exclude" ? "exclude" : "include",
  );
  const [catalog, setCatalog] = useState<TrafficService[]>([]);
  const [loading, setLoading] = useState(true);
  const [unavailable, setUnavailable] = useState(false);
  const [query, setQuery] = useState("");
  const [input, setInput] = useState("");
  const [invalid, setInvalid] = useState(false);
  const [adding, setAdding] = useState(false);
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
        if (!controller.signal.aborted) {
          setCatalog(data);
          setDraft((value) => seedTrafficDefaults(value, data));
        }
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
        <button
          type="button"
          className="traffic-add-service"
          disabled={busy}
          aria-expanded={adding}
          onClick={() => {
            setAdding(!adding);
            setInput("");
            setInvalid(false);
          }}
        >
          <span aria-hidden="true">＋</span> {t("Добавить свой сервис")}
        </button>
        {adding && (
          <div className="traffic-mask-form">
            <label htmlFor="traffic-mask">{t("Маска сервиса")}</label>
            <div className="traffic-mask-entry">
              <input
                id="traffic-mask"
                value={input}
                disabled={busy}
                autoFocus
                placeholder="example.com, *.example.com"
                onChange={(e) => setInput(e.target.value)}
              />
              <button
                type="button"
                disabled={busy || !input.trim()}
                onClick={() => {
                  try {
                    const masks = [
                      ...new Set([
                        ...list.masks,
                        ...input.split(/[,\n]+/).map(normalizeMask),
                      ]),
                    ];
                    if (masks.length > 256) throw new Error();
                    setDraft({
                      ...draft,
                      preset_defaults: false,
                      [tab]: { ...list, masks },
                    });
                    setInput("");
                    setInvalid(false);
                    setAdding(false);
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
          </div>
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
                    preset_defaults: false,
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
        {serviceGroups(
          services,
          tab,
          getLanguage(),
          initial[tab].services.map((s) => s.id),
        ).map((group) => (
          <section
            key={group.key}
            className="traffic-category"
            aria-label={t(group.title)}
            data-testid={`traffic-group-${group.key}`}
          >
            <h3>{t(group.title)}</h3>
            <div className="traffic-services">
              {group.services
                .filter((service) =>
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
                          preset_defaults: false,
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
            void onSave({
              ...refreshServices(draft, catalog),
              preset_defaults: false,
            }).catch(() => {});
          }}
        >
          {t("Сохранить")}
        </button>
      </div>
    </dialog>
  );
}
