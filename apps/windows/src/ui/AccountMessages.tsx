import { t, useLanguage, getLanguage } from "../i18n";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useApplication } from "../state/application";
import { ProductText as MessageLabel } from "./ProductText";
import { messageBrowser as nativeMessageBrowser } from "../native/messageBrowser";
import {
  MessagesError,
  messageExpired,
  messageKey,
  type AccountMessage,
  type MessageAction,
  type MessagesClient,
} from "../messages/model";

export function AccountMessages({ version }: { readonly version: string }) {
  useLanguage();
  const { session, messages } = useApplication();
  const active = useSyncExternalStore(
    session.subscribe,
    session.current,
    session.current,
  );
  const { pathname } = useLocation();
  if (
    !active ||
    active.plan === "DEMO" ||
    !messages ||
    pathname === "/login" ||
    pathname === "/auth/verify-otp" ||
    !/^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.+-]+)?$/.test(version)
  )
    return null;
  return (
    <MessageVisit
      key={`${active.userId}:${active.sessionId}`}
      client={messages}
      version={version}
    />
  );
}

function MessageVisit({
  client,
  version,
}: {
  readonly client: MessagesClient;
  readonly version: string;
}) {
  useLanguage();
  const { session } = useApplication();
  const navigate = useNavigate();
  const [queue, setQueue] = useState<readonly AccountMessage[]>([]);
  const [blocked, setBlocked] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(false);
  const seen = useRef(new Set<string>());
  const [openedLinks, setOpenedLinks] = useState<ReadonlySet<string>>(
    new Set(),
  );
  const confirming = useRef(false);
  const alive = useRef(true);
  const confirmation = useRef<AbortController | null>(null);
  const message = queue[0];
  const canClose =
    message?.dismissal_mode !== "REQUIRE_LINK" ||
    openedLinks.has(messageKey(message));

  useEffect(() => {
    alive.current = true;
    let disposed = false;
    let loading = false;
    let retry = true;
    let requiredKnown = false;
    let lastAttempt = -Infinity;
    let controller: AbortController | null = null;
    const load = async () => {
      if (disposed || loading || !retry || Date.now() - lastAttempt < 10000)
        return;
      const active = session.current();
      if (!active) return;
      lastAttempt = Date.now();
      loading = true;
      controller = new AbortController();
      try {
        const next = await client.list(
          active.accessToken,
          {
            platform: "WINDOWS",
            app_version: version,
            locale: {
              ru: "ru-RU",
              en: "en-GB",
              zh: "zh-CN",
              es: "es-ES",
              de: "de-DE",
              fr: "fr-FR",
            }[getLanguage()],
            schema_version: 2,
          },
          controller.signal,
        );
        if (
          disposed ||
          controller.signal.aborted ||
          session.current()?.sessionId !== active.sessionId
        )
          return;
        requiredKnown = next.some(
          (item) =>
            item.dismissal_mode === "REQUIRE_LINK" &&
            !messageExpired(item) &&
            !seen.current.has(messageKey(item)),
        );
        retry = requiredKnown;
        setQueue(
          next.filter(
            (item) =>
              !messageExpired(item) && !seen.current.has(messageKey(item)),
          ),
        );
      } catch (cause) {
        if (
          !requiredKnown &&
          cause instanceof MessagesError &&
          (cause.code === "UNSUPPORTED" ||
            cause.code === "AUTH_INVALID" ||
            cause.code === "INVALID_RESPONSE")
        )
          retry = false;
      } finally {
        loading = false;
      }
    };
    void load();
    const retryLoad = () => void load();
    window.addEventListener("online", retryLoad);
    window.addEventListener("focus", retryLoad);
    const timer = window.setInterval(retryLoad, 30000);
    return () => {
      disposed = true;
      alive.current = false;
      controller?.abort();
      confirmation.current?.abort();
      window.removeEventListener("online", retryLoad);
      window.removeEventListener("focus", retryLoad);
      window.clearInterval(timer);
    };
  }, [client, session, version]);

  useEffect(() => {
    if (!message) return;
    const check = () =>
      setBlocked(
        Array.from(
          document.querySelectorAll('dialog[open], [aria-modal="true"]'),
        ).some((node) => !node.hasAttribute("data-account-message")),
      );
    check();
    const observer = new MutationObserver(check);
    observer.observe(document.body, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ["open", "aria-modal"],
    });
    return () => observer.disconnect();
  }, [message]);

  useEffect(() => {
    if (!message?.expires_at) return;
    const timer = setTimeout(
      () => {
        confirmation.current?.abort();
        confirming.current = false;
        setPending(false);
        setError(false);
        setQueue((items) => items.filter((item) => !messageExpired(item)));
      },
      Math.max(
        0,
        Math.min(2147483647, Date.parse(message.expires_at) - Date.now()),
      ),
    );
    return () => clearTimeout(timer);
  }, [message, queue]);

  function later() {
    if (!message || !canClose || message.dismissal_mode === "ONCE") return;
    confirmation.current?.abort();
    confirming.current = false;
    setPending(false);
    setError(false);
    seen.current.add(messageKey(message));
    setQueue((items) => items.slice(1));
  }

  async function acknowledge(action?: MessageAction) {
    if (
      !message ||
      !["ONCE", "LEGACY"].includes(message.dismissal_mode) ||
      confirming.current ||
      messageExpired(message)
    )
      return;
    const active = session.current();
    if (!active) return;
    confirming.current = true;
    setPending(true);
    setError(false);
    const controller = new AbortController();
    confirmation.current = controller;
    try {
      await client.acknowledge(active.accessToken, message, controller.signal);
      if (
        !alive.current ||
        controller.signal.aborted ||
        session.current()?.sessionId !== active.sessionId
      )
        return;
      seen.current.add(messageKey(message));
      setQueue((items) =>
        items.filter((item) => messageKey(item) !== messageKey(message)),
      );
      if (action)
        navigate(
          {
            OPEN_SUBSCRIPTION: "/settings/subscription",
            OPEN_SETTINGS: "/settings",
            OPEN_ABOUT: "/about",
          }[action.type],
        );
    } catch {
      if (alive.current && !controller.signal.aborted) setError(true);
    } finally {
      if (confirmation.current === controller) {
        confirming.current = false;
        if (alive.current) setPending(false);
      }
    }
  }

  if (
    !message ||
    (blocked && message.dismissal_mode !== "REQUIRE_LINK") ||
    messageExpired(message)
  )
    return null;
  return (
    <MessageDialog
      key={messageKey(message)}
      message={t(message)}
      pending={pending}
      error={error}
      canClose={canClose}
      onClose={() => {
        if (canClose) {
          if (message.dismissal_mode === "ONCE") void acknowledge();
          else later();
        }
      }}
      onLinkOpened={() =>
        setOpenedLinks((keys) => new Set(keys).add(messageKey(message)))
      }
      onAcknowledge={(action) => void acknowledge(action)}
    />
  );
}

function MessageDialog({
  message,
  pending,
  error,
  canClose,
  onClose,
  onLinkOpened,
  onAcknowledge,
}: {
  readonly message: AccountMessage;
  readonly pending: boolean;
  readonly error: boolean;
  readonly canClose: boolean;
  readonly onClose: () => void;
  readonly onLinkOpened: () => void;
  readonly onAcknowledge: (action?: MessageAction) => void;
}) {
  useLanguage();
  const { messageBrowser = nativeMessageBrowser } = useApplication();
  const [linkError, setLinkError] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    dialog.current?.showModal();
    return () => previous?.focus();
  }, []);
  return (
    <dialog
      ref={dialog}
      className="account-message"
      data-account-message="true"
      aria-labelledby="account-message-title"
      onCancel={(event) => {
        event.preventDefault();
        if (canClose && !pending) onClose();
      }}
    >
      <div className="account-message-heading">
        <span>
          {t(
            message.kind === "promotion"
              ? "предложение"
              : message.kind === "update"
                ? "обновление"
                : "сообщение",
          )}
        </span>
        {canClose ? (
          <button
            type="button"
            className="account-message-close"
            aria-label={t(
              message.dismissal_mode === "LEGACY"
                ? "показать сообщение позже"
                : "закрыть",
            )}
            disabled={pending}
            onClick={onClose}
          >
            ×
          </button>
        ) : null}
      </div>
      <h2 id="account-message-title">
        <MessageLabel text={message.title} />
      </h2>
      <div className="account-message-content">
        {message.blocks.map((block, index) =>
          block.type === "paragraph" ? (
            <p key={index}>
              <MessageLabel text={block.text} />
            </p>
          ) : (
            <ul key={index}>
              {block.items.map((item, position) => (
                <li key={position}>
                  <MessageLabel text={item} />
                </li>
              ))}
            </ul>
          ),
        )}
      </div>
      {message.links.length > 0 ? (
        <div className="account-message-links">
          {message.links.map((link, index) => (
            <button
              type="button"
              key={index}
              onClick={() => {
                setLinkError(false);
                void messageBrowser
                  .open(link.url)
                  .then(onLinkOpened)
                  .catch(() => setLinkError(true));
              }}
            >
              <MessageLabel text={link.label} />
            </button>
          ))}
        </div>
      ) : null}
      {linkError ? (
        <p role="alert">{t("не удалось открыть ссылку. попробуйте ещё раз")}</p>
      ) : null}
      {error ? (
        <p className="account-message-error" role="alert">
          {t("не удалось сохранить подтверждение. попробуйте ещё раз")}
        </p>
      ) : null}
      {canClose ? (
        <div className="account-message-actions">
          {message.dismissal_mode === "LEGACY" ? (
            <button
              type="button"
              className="account-message-later"
              onClick={onClose}
            >
              {t("позже")}
            </button>
          ) : null}
          <button
            type="button"
            disabled={pending}
            onClick={() =>
              message.dismissal_mode === "LEGACY" ? onAcknowledge() : onClose()
            }
          >
            <MessageLabel
              text={pending ? t("сохраняем…") : message.dismiss_label}
            />
          </button>
          {message.primary_action ? (
            <button
              type="button"
              className="account-message-primary"
              disabled={pending}
              onClick={() => onAcknowledge(message.primary_action ?? undefined)}
            >
              <MessageLabel text={message.primary_action.label} />
            </button>
          ) : null}
        </div>
      ) : null}
    </dialog>
  );
}
