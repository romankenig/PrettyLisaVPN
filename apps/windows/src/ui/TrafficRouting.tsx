import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { t, useLanguage } from "../i18n";
import { useApplication } from "../state/application";
import {
  getDeviceTrafficSelection,
  normalizeMask,
  parseTrafficCatalog,
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
      <h2 id="traffic-mode-title">{t("что защищаем")}</h2>
      <fieldset className="traffic-mode__options" disabled={busy}>
        <legend className="sr-only">{t("режим трафика")}</legend>
        {(["all", "include", "exclude"] as Mode[]).map((mode) => (
          <label
            key={mode}
            className={`traffic-choice ${mode === selected.mode ? "traffic-choice--active" : ""}`}
          >
            <input
              type="radio"
              name="traffic-mode"
              value={mode}
              checked={mode === selected.mode}
              onChange={() => {
                void save({ ...selected, mode }).catch(() => {});
              }}
            />
            <span className="traffic-choice__icon" aria-hidden="true">
              {mode === "all" ? "◇" : mode === "include" ? "+" : "−"}
            </span>
            <span>
              <strong>{t(labels[mode])}</strong>
              <small>{t(details[mode])}</small>
            </span>
          </label>
        ))}
      </fieldset>
      <button type="button" disabled={busy} onClick={() => setOpen(true)}>
        {t("Выбрать сервисы")}
      </button>
      {error && (
        <p role="alert">
          {t("Не удалось сохранить правила. Повторите попытку.")}
        </p>
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
function ServiceIcon({ name }: { name: string }) {
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
      {name === "youtube" ? (
        <>
          <rect x="2" y="5" width="20" height="14" rx="4" />
          <path fill="currentColor" stroke="none" d="m10 9 6 3-6 3z" />
        </>
      ) : name === "instagram" ? (
        <>
          <rect x="3" y="3" width="18" height="18" rx="5" />
          <circle cx="12" cy="12" r="4" />
          <circle cx="17.5" cy="6.5" r=".7" />
        </>
      ) : (
        <circle cx="12" cy="12" r="9" />
      )}
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
      className="billing-dialog traffic-dialog"
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
        <div className="traffic-services">
          {services.map((service) => (
            <label key={service.id}>
              <input
                type="checkbox"
                aria-label={service.name}
                checked={list.services.some((s) => s.id === service.id)}
                disabled={busy}
                onChange={() =>
                  setDraft({
                    ...draft,
                    [tab]: {
                      ...list,
                      services: list.services.some((s) => s.id === service.id)
                        ? list.services.filter((s) => s.id !== service.id)
                        : [...list.services, service],
                    },
                  })
                }
              />
              <ServiceIcon name={service.icon} />
              <span>
                {service.name}
                <small>{service.domains.join(", ")}</small>
              </span>
            </label>
          ))}
        </div>
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
            void onSave(draft).catch(() => {});
          }}
        >
          {t("Сохранить")}
        </button>
      </div>
    </dialog>
  );
}
